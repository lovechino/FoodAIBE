# BA – Business Analysis: AI Food API

## 1. Mô Tả Dự Án
API backend để tư vấn ẩm thực thông minh cho người dùng tại 6 thành phố Việt Nam (Hà Nội, TP.HCM, Đà Nẵng, Hải Phòng, Hạ Long, Thanh Hóa).

**Ngoài phạm vi:** đặt bàn, thanh toán, giao đồ ăn, review người dùng.

---

## 2. Actors

| Actor | Mô tả |
|-------|-------|
| **Mobile Client** (React Native) | Gọi REST API và WebSocket để chat |
| **Admin** | Upload data pack, deploy server |

---

## 3. Use Cases

### UC1 – Hỏi về món ăn / quán ăn
- **Actor:** Mobile Client
- **Input:** Câu hỏi text (VD: "tôi muốn ăn phở")
- **Xử lý:** Router → Simple Handler → Template response (không gọi AI)
- **Output:** Danh sách quán, giá, địa chỉ
- **BR:** Không gọi Gemini → chi phí $0

### UC2 – So sánh giá
- **Actor:** Mobile Client
- **Input:** "so sánh giá bún chả và phở"
- **Xử lý:** Parse intent → tìm giá 2 món song song → template
- **Output:** Bảng giá so sánh
- **BR:** Không gọi Gemini

### UC3 – Tìm quán gần user
- **Actor:** Mobile Client
- **Input:** `POST /nearby` + `user_address` (text) + `query`
- **Xử lý:** FAISS search → Gemini Flash xếp hạng theo địa lý
- **Output:** TOP 5 quán gần nhất, lý do
- **BR:** Dùng Gemini Flash ≤ 800 tokens

### UC4 – Gợi ý theo thời gian thực
- **Actor:** Mobile Client
- **Input:** `GET /suggest?city=ha_noi`
- **Xử lý:** Giờ hiện tại → bữa ăn tương ứng → FAISS → Gemini tổng hợp
- **Output:** 2–3 món phù hợp + lý do
- **Output time map:**
  - 6–9h: Bữa sáng (phở, bún, bánh mì)
  - 10–13h: Bữa trưa (cơm, bún, mì)
  - 14–16h: Xế chiều (ăn vặt, chè)
  - 17–20h: Bữa tối (lẩu, nướng, cơm)
  - 21–5h: Ăn đêm (cháo, mì)

### UC5 – Tìm kiếm trực tiếp
- **Actor:** Mobile Client
- **Input:** `GET /search?q=keyword&city=ha_noi`
- **Xử lý:** Hybrid search (text match ưu tiên + FAISS semantic)
- **Output:** Danh sách món/quán
- **BR:** Không gọi Gemini

### UC6 – Chat streaming realtime
- **Actor:** Mobile Client
- **Input:** WebSocket frame JSON `{message, city, history, user_address}`
- **Xử lý:** Router → Simple template (instant) HOẶC Gemini stream (chunk-by-chunk)
- **Output:** Text chunks liên tục + done frame
- **BR:** Simple query không stream, trả ngay

---

## 4. Business Rules

| BR | Mô tả |
|----|-------|
| BR1 | Query đơn giản → SimpleHandler, **không gọi Gemini** ($0) |
| BR2 | Query phức tạp → Gemini Flash, maxOutput ≤ 800 tokens |
| BR3 | Query nặng (>200 ký tự, đa tầng) → Gemini Pro, maxOutput ≤ 1500 tokens |
| BR4 | Chat history giữ tối đa 6 turn gần nhất |
| BR5 | Text match (exact) ưu tiên trước semantic search |
| BR6 | FAISS index preload khi startup |

---

## 5. Non-Functional Requirements

| NFR | Yêu cầu |
|-----|---------|
| Latency | Simple query < 200ms, Gemini query < 5s |
| Cost | ≥ 60% requests xử lý không tốn API cost |
| Scalability | Stateless – scale horizontal dễ dàng |
| Maintainability | File ≤ 400 dòng, method ≤ 20 dòng, SRP |
