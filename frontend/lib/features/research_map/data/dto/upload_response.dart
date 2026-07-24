import '../api_exception.dart';

class UploadResponse {
  const UploadResponse({
    required this.paperId,
    required this.filename,
    required this.pageCount,
    required this.chunkCount,
  });

  final String paperId;
  final String filename;
  final int pageCount;
  final int chunkCount;

  factory UploadResponse.fromJson(Map<String, Object?> json) {
    final paperId = _string(json['paper_id']);
    final filename = _string(json['filename']);
    final pageCount = _nonNegativeInt(json['page_count']);
    final chunkCount = _nonNegativeInt(json['chunk_count']);
    return UploadResponse(
      paperId: paperId,
      filename: filename,
      pageCount: pageCount,
      chunkCount: chunkCount,
    );
  }
}

String _string(Object? value) {
  if (value is! String || value.trim().isEmpty) throw const ParseException();
  return value.trim();
}

int _nonNegativeInt(Object? value) {
  if (value is! int || value < 0) throw const ParseException();
  return value;
}
