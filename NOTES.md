# Ghi chú phân tích · Day 04

Họ và tên: Trịnh Quốc Đạt  
MSSV: 2A202603581

## 1. Case được chọn

- **ID case:** A5
- **Câu trả lời của agent:** Lần chạy đầu Agent không tạo được câu trả lời cuối cùng vì hết số bước. Lần chạy thứ hai Agent hoàn thành, liệt kê các incident tìm được và giải thích giới hạn truy vấn 50 incident gần nhất.
- **Điểm ở lần chạy 1:** 0/100.

## 2. Bằng chứng trong trace

Ở lần chạy đầu (`eval_test_A5.json`), Agent thực hiện 8 tool steps. Bước cuối cùng là gọi `get_incident_details` với incident ID `h02n9572mx9y`.

Kết quả:
- `status`: `max_steps`
- `answer`: rỗng
- `tool_calls`: 8
- `tool_steps`: 8
- Judge reason: "Agent hết số bước trước khi hoàn tất."

Nguyên nhân có thể xảy ra: Agent truy vấn chi tiết nhiều incident liên tiếp, khiến số bước cho phép không đủ để hoàn thành việc tổng hợp và tạo câu trả lời cuối cùng.

## 3. Thay đổi đã thực hiện

**Thay đổi 1 – Điều chỉnh cấu hình Evaluation cho case A5**

- Thay đổi: Tăng `--max-steps` từ 8 lên 12 khi chạy lại case A5.
- Lý do: Trace lần đầu cho thấy Agent sử dụng hết 8 bước nhưng chưa tạo được câu trả lời cuối cùng.
- Kết quả: Lần chạy thứ hai hoàn thành với điểm 93/100.

**Thay đổi 2 – Bổ sung Evidence Gate trong `agent.py`**

- Lưu URL từ kết quả `get_incident_details` khi tool thực thi thành công.
- Kiểm tra câu trả lời cuối có chứa URL nguồn đã quan sát hay không.
- Nếu thiếu URL, ghi event `validation_missing_source` vào trace và yêu cầu model chỉnh sửa câu trả lời.
- Không yêu cầu URL nếu tool lấy incident thất bại.
- Nếu hết `max_steps` mà vẫn thiếu URL, Agent trả về `max_steps`, không đánh dấu `completed`.

**Lý do:** Đảm bảo câu trả lời có sự hiện diện của URL nguồn đã được truy xuất thành công, đồng thời không tạo yêu cầu nguồn đối với dữ liệu chưa lấy được.

**Kết quả kiểm thử:**
- `test_missing_url_gets_revision_within_budget`: PASS.
- `test_missing_url_at_budget_limit_is_not_completed`: PASS.
- `test_failed_tool_does_not_require_source`: PASS.
- Toàn bộ `tests/test_validation.py`: 5/5 PASS.
- Toàn bộ unit tests: 37/37 PASS.

Lưu ý: Evidence Gate chỉ kiểm tra sự hiện diện của URL, không chứng minh mọi nhận định trong câu trả lời đều được nguồn hỗ trợ.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_test_A5.json` | `eval_test_A5_v2.json` |
|---|---:|---:|
| Điểm case A5 | 0 | 93 |
| Model calls của Agent | 8 | 2 |
| Prompt tokens | 17.809 | 1.267 |
| Completion tokens | 717 | 1.109 |
| Tổng tokens Agent | 18.526 | 2.376 |
| Judge tokens | Không có | 2.339 |

Lưu ý: Đây là kết quả của hai lần chạy riêng case A5, chưa phải kết quả Evaluation đầy đủ 22 case.

- **Lỗi đã giải quyết:** Agent không hoàn thành do chạm giới hạn 8 bước trong lần chạy đầu. Lần chạy thứ hai đã hoàn thành.
- **Lỗi còn lại hoặc mới xuất hiện:** Câu trả lời vẫn có thể cải thiện bằng cách đề xuất cụ thể hơn phương pháp truy vấn API lịch sử GitHub Status. Judge đề xuất điểm này trong phần improvement.

## 5. Giới hạn

- Điểm Judge là kết quả đánh giá theo tiêu chí và rubric của bộ Evaluation, không đại diện tuyệt đối cho chất lượng Agent trong mọi tình huống.
- Dữ liệu trạng thái GitHub sử dụng snapshot được ghi nhận ngày 09/11/2026, không phải dữ liệu thời gian thực.
- Công cụ chỉ truy xuất tối đa 50 incident gần nhất. Không tìm thấy incident năm 2025 trong phạm vi này không chứng minh rằng năm 2025 không có incident.
- Chỉ chạy một lần cho mỗi cấu hình chưa đủ để kết luận Agent luôn hoạt động ổn định. Kết quả có thể thay đổi do tính ngẫu nhiên của mô hình và dữ liệu đầu vào.
- Việc tăng `max_steps` giúp xử lý case này nhưng không đảm bảo mọi case khác đều được cải thiện.