import '../api_exception.dart';

enum JobStatus { pending, running, succeeded, failed, unknown }

JobStatus jobStatusFromJson(Object? value) {
  if (value is! String) return JobStatus.unknown;
  switch (value) {
    case 'pending':
      return JobStatus.pending;
    case 'running':
      return JobStatus.running;
    case 'succeeded':
      return JobStatus.succeeded;
    case 'failed':
      return JobStatus.failed;
    default:
      return JobStatus.unknown;
  }
}

class JobCreateResponse {
  const JobCreateResponse({
    required this.jobId,
    required this.paperId,
    required this.status,
    this.createdAt,
  });

  final String jobId;
  final String paperId;
  final JobStatus status;
  final DateTime? createdAt;

  factory JobCreateResponse.fromJson(Map<String, Object?> json) {
    return JobCreateResponse(
      jobId: _string(json['job_id']),
      paperId: _string(json['paper_id']),
      status: jobStatusFromJson(json['status']),
      createdAt:
          json['created_at'] == null ? null : _utcDate(json['created_at']),
    );
  }
}

class JobStatusResponse {
  const JobStatusResponse({
    required this.jobId,
    required this.paperId,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    required this.error,
  });

  final String jobId;
  final String paperId;
  final JobStatus status;
  final DateTime createdAt;
  final DateTime updatedAt;
  final String? error;

  factory JobStatusResponse.fromJson(Map<String, Object?> json) {
    final error = json['error'];
    return JobStatusResponse(
      jobId: _string(json['job_id']),
      paperId: _string(json['paper_id']),
      status: jobStatusFromJson(json['status']),
      createdAt: _utcDate(json['created_at']),
      updatedAt: _utcDate(json['updated_at']),
      error: error == null ? null : _string(error),
    );
  }
}

String _string(Object? value) {
  if (value is! String || value.trim().isEmpty) throw const ParseException();
  return value.trim();
}

DateTime _utcDate(Object? value) {
  if (value is! String) throw const ParseException();
  final parsed = DateTime.tryParse(value);
  if (parsed == null) throw const ParseException();
  return parsed.toUtc();
}
