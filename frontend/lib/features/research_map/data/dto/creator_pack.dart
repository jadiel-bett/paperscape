import '../api_exception.dart';

enum CreatorAudience { generalPublic, highSchool, undergraduate }

String audienceValue(CreatorAudience value) => switch (value) {
      CreatorAudience.generalPublic => 'general_public',
      CreatorAudience.highSchool => 'high_school',
      CreatorAudience.undergraduate => 'undergraduate',
    };

class CreatorPack {
  const CreatorPack({
    required this.packId,
    required this.paperId,
    required this.audience,
    required this.status,
    required this.title,
    required this.summary,
    required this.narrationScript,
    required this.visualAbstract,
    required this.evidenceCards,
    required this.limitations,
    required this.disclaimer,
  });

  final String packId;
  final String paperId;
  final String audience;
  final String status;
  final String title;
  final String summary;
  final String narrationScript;
  final List<CreatorBlock> visualAbstract;
  final List<CreatorEvidenceCard> evidenceCards;
  final List<String> limitations;
  final String disclaimer;

  factory CreatorPack.fromJson(Map<String, Object?> json) => CreatorPack(
        packId: _text(json['pack_id']),
        paperId: _text(json['paper_id']),
        audience: _text(json['audience']),
        status: _text(json['status']),
        title: _text(json['title']),
        summary: _text(json['summary']),
        narrationScript: _text(json['narration_script']),
        visualAbstract: _objects(json['visual_abstract'])
            .map(CreatorBlock.fromJson)
            .toList(),
        evidenceCards: _objects(json['evidence_cards'])
            .map(CreatorEvidenceCard.fromJson)
            .toList(),
        limitations: _strings(json['limitations']),
        disclaimer: _text(json['disclaimer']),
      );
}

class CreatorBlock {
  const CreatorBlock({required this.label, required this.text});
  final String label;
  final String text;
  factory CreatorBlock.fromJson(Map<String, Object?> json) =>
      CreatorBlock(label: _text(json['label']), text: _text(json['text']));
}

class CreatorEvidenceCard {
  const CreatorEvidenceCard({
    required this.statement,
    required this.confidence,
    required this.evidenceIds,
  });
  final String statement;
  final String confidence;
  final List<String> evidenceIds;
  factory CreatorEvidenceCard.fromJson(Map<String, Object?> json) =>
      CreatorEvidenceCard(
        statement: _text(json['statement']),
        confidence: _text(json['confidence']),
        evidenceIds: _strings(json['evidence_ids']),
      );
}

String _text(Object? value) {
  if (value is! String || value.trim().isEmpty) throw const ParseException();
  return value.trim();
}

List<Map<String, Object?>> _objects(Object? value) {
  if (value is! List) throw const ParseException();
  return value.map((item) {
    if (item is! Map<String, Object?>) throw const ParseException();
    return item;
  }).toList();
}

List<String> _strings(Object? value) {
  if (value is! List) throw const ParseException();
  return value.map(_text).toList();
}
