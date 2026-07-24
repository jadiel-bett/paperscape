import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/features/research_map/data/api_exception.dart';

void main() {
  test('parses backend detail code and message', () {
    final error = parseApiError(
      400,
      '{"detail":{"code":"invalid_upload","message":"Safe message"}}',
    );

    expect(error.statusCode, 400);
    expect(error.code, 'invalid_upload');
    expect(error.safeMessage, 'Safe message');
  });

  test('malformed json becomes generic safe error', () {
    final error = parseApiError(500, '{bad json');

    expect(error.code, 'http_error');
    expect(error.safeMessage, 'Something went wrong. Please try again.');
  });

  test('html response becomes generic safe error', () {
    final error = parseApiError(500, '<html>secret body</html>');

    expect(error.code, 'http_error');
    expect(error.safeMessage, 'Something went wrong. Please try again.');
    expect(error.toString().contains('secret body'), isFalse);
  });

  test('unknown response shape becomes generic safe error', () {
    final error = parseApiError(500, '{"unexpected":true}');

    expect(error.code, 'http_error');
    expect(error.safeMessage, 'Something went wrong. Please try again.');
  });
}
