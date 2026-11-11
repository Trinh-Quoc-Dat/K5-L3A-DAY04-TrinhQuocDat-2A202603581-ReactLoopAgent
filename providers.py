"""Bốn provider cùng một interface. Không chứa agent loop."""
import json
import os
import urllib.error
import urllib.request
import time
import re

CONFIG = {
    'openai': ('OPENAI_API_KEY', 'https://api.openai.com/v1/chat/completions'),
    'gemini': ('GEMINI_API_KEY', 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'),
    'openrouter': ('OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1/chat/completions'),
    'anthropic': ('ANTHROPIC_API_KEY', 'https://api.anthropic.com/v1/messages'),
    'groq': ('GROQ_API_KEY', 'https://api.groq.com/openai/v1/chat/completions'),
}



def post_json(url, headers, payload):
    max_attempts = 4

    def parse_duration(value):
        if not value:
            return 0

        value = str(value).strip()

        try:
            return float(value)
        except ValueError:
            pass

        match = re.fullmatch(
            r'(?:(\d+(?:\.\d+)?)h)?'
            r'(?:(\d+(?:\.\d+)?)m)?'
            r'(?:(\d+(?:\.\d+)?)s)?',
            value
        )

        if not match:
            return 0

        hours, minutes, seconds = match.groups()

        return (
            float(hours or 0) * 3600
            + float(minutes or 0) * 60
            + float(seconds or 0)
        )

    for attempt in range(max_attempts):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                **headers,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'ReactLoopAgent/1.0',
            },
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response)

        except urllib.error.HTTPError as exc:
            response_headers = exc.headers or {}

            header_names = [
                'retry-after',
                'x-ratelimit-limit-requests',
                'x-ratelimit-remaining-requests',
                'x-ratelimit-reset-requests',
                'x-ratelimit-limit-tokens',
                'x-ratelimit-remaining-tokens',
                'x-ratelimit-reset-tokens',
            ]

            details = []
            for name in header_names:
                value = response_headers.get(name)
                if value is not None:
                    details.append(f'{name}: {value!r}')

            diagnostic = '; '.join(details) or 'Không có rate-limit headers'

            if exc.code == 429 and attempt < max_attempts - 1:
                retry_after = parse_duration(
                    response_headers.get('retry-after')
                )
                reset_tokens = parse_duration(
                    response_headers.get('x-ratelimit-reset-tokens')
                )

                wait_seconds = max(
                    retry_after,
                    reset_tokens,
                    2 ** (attempt + 1)
                ) + 1

                print(
                    f'HTTP 429: Chờ {wait_seconds:.1f} giây '
                    f'rồi thử lại ({attempt + 1}/{max_attempts - 1})...'
                )

                exc.close()
                time.sleep(wait_seconds)
                continue

            raise RuntimeError(
                f'Provider trả HTTP {exc.code}; {diagnostic}'
            ) from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f'Không kết nối được provider: {exc.reason}'
            ) from exc
        
class Provider:
    """complete(messages, schemas) -> {message, calls, finish, usage}.

    messages: system/user/assistant/tool theo format Chat Completions. message trả về
    cần được append nguyên vẹn; tool result có role, tool_call_id, content (JSON string).
    """
    def __init__(self, name, model):
        if name not in CONFIG:
            raise ValueError(f'Provider không hợp lệ: {name}')
        if not model:
            raise ValueError('Cần đặt MODEL là model có hỗ trợ tool calling.')
        self.name, self.model = name, model
        key_name, self.url = CONFIG[name]
        self.key = os.getenv(key_name)
        if not self.key:
            raise ValueError(f'Thiếu {key_name}; xem README.md.')

    def complete(self, messages, schemas):
        if self.name == 'anthropic':
            return self._anthropic(messages, schemas)
        payload = {'model': self.model, 'messages': messages}
        if schemas:
            payload['tools'] = schemas
        data = post_json(self.url, {'Authorization': f'Bearer {self.key}'}, payload)
        choice = data['choices'][0]
        message = choice['message']
        calls = [{'id': c['id'], 'name': c['function']['name'], 'arguments': c['function']['arguments']} for c in message.get('tool_calls', [])]
        return {'message': message, 'calls': calls, 'finish': choice.get('finish_reason'), 'usage': data.get('usage', {})}

    def _anthropic(self, messages, schemas):
        system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
        native = []
        for m in messages:
            if m['role'] == 'system':
                continue
            if m['role'] == 'assistant':
                blocks = []
                if m.get('content'):
                    blocks.append({'type': 'text', 'text': m['content']})
                for call in m.get('tool_calls', []):
                    blocks.append({'type': 'tool_use', 'id': call['id'], 'name': call['function']['name'], 'input': json.loads(call['function']['arguments'])})
                native.append({'role': 'assistant', 'content': blocks})
            elif m['role'] == 'tool':
                block = {'type': 'tool_result', 'tool_use_id': m['tool_call_id'], 'content': m['content']}
                if native and native[-1]['role'] == 'user' and isinstance(native[-1]['content'], list):
                    native[-1]['content'].append(block)
                else:
                    native.append({'role': 'user', 'content': [block]})
            else:
                native.append({'role': 'user', 'content': m['content']})
        tools = [{'name': x['function']['name'], 'description': x['function']['description'], 'input_schema': x['function']['parameters']} for x in schemas]
        payload = {'model': self.model, 'max_tokens': 1024, 'system': system, 'messages': native}
        if tools:
            payload['tools'] = tools
        data = post_json(self.url, {'x-api-key': self.key, 'anthropic-version': '2023-06-01'}, payload)
        blocks = data['content']
        calls = [{'id': b['id'], 'name': b['name'], 'arguments': json.dumps(b['input'], ensure_ascii=False)} for b in blocks if b['type'] == 'tool_use']
        text = '\n'.join(b['text'] for b in blocks if b['type'] == 'text')
        message = {'role': 'assistant', 'content': text or None}
        if calls:
            message['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['name'], 'arguments': c['arguments']}} for c in calls]
        reason = {'end_turn': 'stop', 'tool_use': 'tool_calls', 'max_tokens': 'length'}.get(data.get('stop_reason'), data.get('stop_reason'))
        return {'message': message, 'calls': calls, 'finish': reason, 'usage': data.get('usage', {})}
