import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/features/research_map/data/api_exception.dart';
import 'package:frontend/features/research_map/data/dto/upload_response.dart';

void main() {
  test('valid upload response parses', () {
    final response = UploadResponse.fromJson({
      'paper_id': 'paper-1',
      'filename': 'paper.pdf',
      'page_count': 3,
      'chunk_count': 9,
      'extra': 'ignored',
    });

    expect(response.paperId, 'paper-1');
    expect(response.filename, 'paper.pdf');
    expect(response.pageCount, 3);
    expect(response.chunkCount, 9);
  });

  test('missing required field fails safely', () {
    expect(
      () => UploadResponse.fromJson({
        'paper_id': 'paper-1',
        'filename': 'paper.pdf',
        'page_count': 3,
      }),
      throwsA(isA<ApiException>()),
    );
  });

  test('wrong field type fails safely', () {
    expect(
      () => UploadResponse.fromJson({
        'paper_id': 'paper-1',
        'filename': 'paper.pdf',
        'page_count': '3',
        'chunk_count': 9,
      }),
      throwsA(isA<ApiException>()),
    );
  });
}
