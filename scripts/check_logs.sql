-- 대화 로그 확인용 SQL (psql에서 실행)
-- 사용 예: psql "$DATABASE_URL" -v email='user@example.com' -f scripts/check_logs.sql

-- 1. 사용자별 저장된 대화 수와 마지막 대화 시각
SELECT u.id AS user_id, u.email, COUNT(c.id) AS chat_count, MAX(c.created_at) AS last_chat_at
FROM users u
LEFT JOIN chat_logs c ON c.user_id = u.id
GROUP BY u.id, u.email
ORDER BY u.id;

-- 2. 한 사용자의 최근 대화 20건 (질문·답변은 앞 50자만 표시)
SELECT c.id, c.created_at, LEFT(c.question, 50) AS question, LEFT(c.answer, 50) AS answer
FROM chat_logs c
JOIN users u ON u.id = c.user_id
WHERE u.email = :'email'
ORDER BY c.created_at DESC, c.id DESC
LIMIT 20;
