import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/features/research_map/data/api_exception.dart';
import 'package:frontend/features/research_map/data/dto/research_map.dart';

Map<String, Object?> buildMap(
    {int findings = 3, String disclaimer = fixedDisclaimer}) {
  return {
    'paper_id': 'paper-1',
    'research_question': 'What is the effect?',
    'findings': List.generate(findings, (index) {
      final confidence = ['high', 'partial', 'uncertain'][index % 3];
      return {
        'statement': 'Finding ${index + 1}',
        'confidence': confidence,
        'evidence': [
          {
            'chunk_id': 'chunk-${index + 1}',
            'page': 1,
            'excerpt': 'Excerpt ${index + 1}',
          },
          {
            'chunk_id': 'chunk-${index + 1}-b',
            'page': 2,
            'excerpt': 'Excerpt ${index + 1}b',
          },
        ],
      };
    }),
    'limitations': ['Small sample'],
    'disclaimer': disclaimer,
    'extra': 'ignored',
  };
}

void main() {
  test('valid research map parses', () {
    final map = ResearchMap.fromJson(buildMap());

    expect(map.findings, hasLength(3));
    expect(map.findings.first.evidence, hasLength(2));
    expect(map.findings[0].confidence, FindingConfidence.high);
    expect(map.findings[1].confidence, FindingConfidence.partial);
    expect(map.findings[2].confidence, FindingConfidence.uncertain);
    expect(map.findings.first.evidence.first.chunkId, 'chunk-1');
    expect(map.findings.first.evidence.first.page, 1);
    expect(map.disclaimer, fixedDisclaimer);
  });

  test('exactly three findings required', () {
    expect(() => ResearchMap.fromJson(buildMap(findings: 2)),
        throwsA(isA<ApiException>()));
    expect(() => ResearchMap.fromJson(buildMap(findings: 4)),
        throwsA(isA<ApiException>()));
  });

  test('changed disclaimer is rejected', () {
    expect(
      () => ResearchMap.fromJson(buildMap(disclaimer: 'Changed disclaimer')),
      throwsA(isA<ApiException>()),
    );
  });
}
