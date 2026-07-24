import 'dart:convert';

class ApiException implements Exception {
  const ApiException({
    this.statusCode,
    required this.code,
    required this.safeMessage,
  });

  final int? statusCode;
  final String code;
  final String safeMessage;

  @override
  String toString() => 'ApiException($statusCode, $code)';
}

class ParseException extends ApiException {
  const ParseException()
      : super(
          code: 'parse_error',
          safeMessage: 'Something went wrong. Please try again.',
        );
}

ApiException parseApiError(int statusCode, String body) {
  try {
    final decoded = jsonDecode(body);
    if (decoded is Map<String, Object?>) {
      final detail = decoded['detail'];
      if (detail is Map<String, Object?>) {
        final code = detail['code'];
        final message = detail['message'];
        if (code is String &&
            code.trim().isNotEmpty &&
            message is String &&
            message.trim().isNotEmpty) {
          return ApiException(
            statusCode: statusCode,
            code: code.trim(),
            safeMessage: message.trim(),
          );
        }
      }
    }
  } catch (_) {
    // Intentionally ignore malformed/HTML bodies.
  }
  return ApiException(
    statusCode: statusCode,
    code: 'http_error',
    safeMessage: safeMessageForCode('http_error'),
  );
}

String safeMessageForCode(String? code) {
  switch (code) {
    case 'invalid_upload':
      return 'Choose a non-empty PDF file and try again.';
    case 'unsupported_media_type':
      return 'PaperScape accepts PDF files only.';
    case 'upload_not_a_pdf':
      return 'The selected file does not appear to be a PDF. Choose a different file.';
    case 'upload_too_large':
      return 'The PDF is larger than the allowed upload limit. Choose a smaller file.';
    case 'extraction_failed':
      return 'PaperScape could not extract selectable text from this PDF. OCR is not supported in this version.';
    case 'paper_not_found':
      return 'This uploaded paper could not be found. Start over and upload again.';
    case 'job_not_found':
      return 'This research-map job could not be found. Start over and try again.';
    case 'map_not_found':
      return 'The research map is not available yet. Try again after the job completes.';
    case 'generation_unavailable':
      return 'Research-map generation is unavailable. Check backend configuration, then retry.';
    case 'task_scheduling_failed':
      return 'PaperScape could not start the background job. Please try again.';
    case 'persistence_error':
      return 'A storage error occurred. Please try again.';
    case 'server_restart':
      return 'The server restarted before this job completed. Please retry generation.';
    case 'extraction_missing':
      return 'The extracted paper content is missing. Start over and upload again.';
    case 'map_generation_failed':
      return 'PaperScape could not generate a grounded research map for this paper.';
    case 'llm_provider_error':
      return 'The model service was unavailable. Please try again later.';
    case 'invalid_identifier':
      return 'The paper or job identifier is invalid. Start over and try again.';
    default:
      return 'Something went wrong. Please try again.';
  }
}
