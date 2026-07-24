import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/features/research_map/data/api_exception.dart';
import 'package:frontend/features/research_map/data/dto/job_response.dart';

void main() {
  test('job create response parses', () {
    final response = JobCreateResponse.fromJson({
      'job_id': 'job-1',
      'paper_id': 'paper-1',
      'status': 'pending',
      'extra': true,
    });

    expect(response.jobId, 'job-1');
    expect(response.paperId, 'paper-1');
    expect(response.status, JobStatus.pending);
  });

  test('job status response parses all known statuses', () {
    for (final status in ['pending', 'running', 'succeeded', 'failed']) {
      final response = JobStatusResponse.fromJson({
        'job_id': 'job-1',
        'paper_id': 'paper-1',
        'status': status,
        'created_at': '2026-01-01T00:00:00+00:00',
        'updated_at': '2026-01-01T00:00:01+00:00',
        'error': status == 'failed' ? 'map_generation_failed' : null,
        'extra': 'ignored',
      });

      expect(response.createdAt.isUtc, isTrue);
      expect(response.updatedAt.isUtc, isTrue);
    }
  });

  test('unknown status handled safely', () {
    expect(jobStatusFromJson('future_status'), JobStatus.unknown);
  });

  test('malformed timestamp fails safely', () {
    expect(
      () => JobStatusResponse.fromJson({
        'job_id': 'job-1',
        'paper_id': 'paper-1',
        'status': 'pending',
        'created_at': 'bad',
        'updated_at': 'bad',
        'error': null,
      }),
      throwsA(isA<ApiException>()),
    );
  });

  test('missing required field fails safely', () {
    expect(
      () => JobCreateResponse.fromJson({'job_id': 'job-1'}),
      throwsA(isA<ApiException>()),
    );
  });
}
