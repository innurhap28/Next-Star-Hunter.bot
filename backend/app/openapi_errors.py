"""OpenAPI error contracts for the account routes.

These declarations describe the existing handlers and do not transform runtime
responses. Examples are checked against actual HTTP responses in backend tests.
"""
from .schemas import ErrorResponse, ValidationErrorResponse


def error_response(description, examples, model=ErrorResponse):
    return {
        "model": model,
        "description": description,
        "content": {"application/json": {"examples": {
            name: {"summary": summary, "value": value}
            for name, summary, value in examples
        }}},
    }


VALIDATION_ERROR = error_response(
    "입력 검증 실패. fields는 오류 위치이며 입력값과 비밀번호는 포함하지 않습니다.",
    [
        ("password", "비밀번호 길이 또는 형식 오류", {
            "error": "VALIDATION_ERROR", "message": "입력 형식을 확인해주세요.",
            "fields": [["body", "password"]],
        }),
        ("email", "이메일 형식 오류", {
            "error": "VALIDATION_ERROR", "message": "입력 형식을 확인해주세요.",
            "fields": [["body", "email"]],
        }),
        ("invalid_json", "JSON 구문 오류 위치 예시", {
            "error": "VALIDATION_ERROR", "message": "입력 형식을 확인해주세요.",
            "fields": [["body", 1]],
        }),
    ], ValidationErrorResponse,
)

ORIGIN_ERROR = error_response(
    "허용되지 않은 브라우저 요청 출처입니다.",
    [("origin_not_allowed", "동일 출처 검사 실패", {
        "error": "ORIGIN_NOT_ALLOWED", "message": "허용되지 않은 요청 출처입니다.",
    })],
)

SERVICE_ERROR = error_response(
    "인증 설정 또는 DB 설정·연결 문제입니다. 응답에는 연결 주소나 비밀번호를 포함하지 않습니다.",
    [
        ("auth_not_configured", "인증용 비밀 키 또는 DB 주소 미설정", {
            "error": "AUTH_NOT_CONFIGURED", "message": "서버 인증 설정을 확인해주세요.",
        }),
        ("db_not_configured", "DB 주소 형식 오류", {
            "error": "DB_NOT_CONFIGURED", "message": "서버 DB 설정을 확인해주세요.",
        }),
        ("db_unavailable", "DB 연결 또는 작업 실패", {
            "error": "DB_UNAVAILABLE",
            "message": "현재 DB 요청을 처리할 수 없습니다. 잠시 후 다시 시도해주세요.",
        }),
    ],
)

LOGIN_REQUIRED = error_response(
    "로그인이 필요하거나 세션에 해당하는 사용자를 찾을 수 없습니다.",
    [
        ("login_required", "로그인되지 않은 요청", {
            "error": "LOGIN_REQUIRED", "message": "로그인이 필요합니다.",
        }),
        ("stale_session", "세션 사용자 없음", {
            "error": "LOGIN_REQUIRED", "message": "다시 로그인해주세요.",
        }),
    ],
)

REGISTER_ERRORS = {
    403: ORIGIN_ERROR,
    409: error_response("이미 가입된 이메일입니다.", [("email_exists", "중복 이메일", {
        "error": "EMAIL_EXISTS", "message": "이미 가입된 이메일입니다.",
    })]),
    422: VALIDATION_ERROR,
    503: SERVICE_ERROR,
}
LOGIN_ERRORS = {
    401: error_response("이메일 또는 비밀번호가 올바르지 않습니다.", [
        ("invalid_credentials", "로그인 실패", {
            "error": "INVALID_CREDENTIALS", "message": "이메일 또는 비밀번호를 확인해주세요.",
        }),
    ]),
    403: ORIGIN_ERROR,
    422: VALIDATION_ERROR,
    503: SERVICE_ERROR,
}
LOGOUT_ERRORS = {401: LOGIN_REQUIRED, 403: ORIGIN_ERROR, 503: SERVICE_ERROR}
ME_ERRORS = {401: LOGIN_REQUIRED, 503: SERVICE_ERROR}
