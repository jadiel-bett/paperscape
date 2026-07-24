import '../api_exception.dart';

enum FindingConfidence { high, partial, uncertain, unknown }

const fixedDisclaimer =
    'This AI-generated explanation is grounded in the uploaded document but does not replace expert review.';

FindingConfidence confidenceFromJson(Object? value) {
  if (value is! String) return FindingConfidence.unknown;
  switch (value) {
    case 'high':
      return FindingConfidence.high;
    case 'partial':
      return FindingConfidence.partial;
    case 'uncertain':
      return FindingConfidence.uncertain;
    default:
      return FindingConfidence.unknown;
  }
}

class ResearchMap {
  const ResearchMap({
    required this.paperId,
    required this.researchQuestion,
    required this.findings,
    required this.limitations,
    required this.disclaimer,
  });

  final String paperId;
  final String researchQuestion;
  final List<Finding> findings;
  final List<String> limitations;
  final String disclaimer;

  factory ResearchMap.fromJson(Map<String, Object?> json) {
    final findings = _list(json['findings']).map(Finding.fromJson).toList();
    if (findings.length != 3) throw const ParseException();
    final limitations = _stringList(json['limitations']);
    if (limitations.isEmpty) throw const ParseException();
    final disclaimer = _string(json['disclaimer']);
    if (disclaimer != fixedDisclaimer) throw const ParseException();
    return ResearchMap(
      paperId: _string(json['paper_id']),
      researchQuestion: _string(json['research_question']),
      findings: findings,
      limitations: limitations,
      disclaimer: disclaimer,
    );
  }
}

class Finding {
  const Finding({
    required this.statement,
    required this.evidence,
    required this.confidence,
  });

  final String statement;
  final List<Evidence> evidence;
  final FindingConfidence confidence;

  factory Finding.fromJson(Map<String, Object?> json) {
    final evidence = _list(json['evidence']).map(Evidence.fromJson).toList();
    if (evidence.isEmpty) throw const ParseException();
    return Finding(
      statement: _string(json['statement']),
      evidence: evidence,
      confidence: confidenceFromJson(json['confidence']),
    );
  }
}

class Evidence {
  const Evidence({
    required this.chunkId,
    required this.page,
    required this.excerpt,
  });

  final String chunkId;
  final int page;
  final String excerpt;

  factory Evidence.fromJson(Map<String, Object?> json) {
    final page = json['page'];
    if (page is! int || page < 1) throw const ParseException();
    return Evidence(
      chunkId: _string(json['chunk_id']),
      page: page,
      excerpt: _string(json['excerpt']),
    );
  }
}

String _string(Object? value) {
  if (value is! String || value.trim().isEmpty) throw const ParseException();
  return value.trim();
}

List<Map<String, Object?>> _list(Object? value) {
  if (value is! List) throw const ParseException();
  return value.map((item) {
    if (item is! Map<String, Object?>) throw const ParseException();
    return item;
  }).toList();
}

List<String> _stringList(Object? value) {
  if (value is! List) throw const ParseException();
  return value.map(_string).toList();
}
