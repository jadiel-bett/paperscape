class AppConfig {
  AppConfig({
    String? apiBaseUrl,
    this.clientMaxUploadBytes = 20 * 1024 * 1024,
  }) : apiBaseUrl = _normalize(
          apiBaseUrl ??
              const String.fromEnvironment(
                'PAPERSCAPE_API_BASE_URL',
                defaultValue: 'http://localhost:8000/api/v1',
              ),
        );

  final String apiBaseUrl;
  final int clientMaxUploadBytes;

  static String _normalize(String value) {
    var normalized = value.trim();
    while (normalized.endsWith('/')) {
      normalized = normalized.substring(0, normalized.length - 1);
    }
    return normalized;
  }
}
