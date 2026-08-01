import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/features/research_map/data/dto/job_response.dart';
import 'package:frontend/features/research_map/data/dto/research_map.dart';
import 'package:frontend/features/research_map/data/dto/upload_response.dart';
import 'package:frontend/features/research_map/data/paperscape_api_client.dart';
import 'package:frontend/features/research_map/domain/pdf_picker.dart';
import 'package:frontend/features/research_map/domain/selected_pdf.dart';
import 'package:frontend/features/research_map/presentation/research_map_controller.dart';
import 'package:frontend/features/research_map/presentation/research_map_screen.dart';
import 'package:frontend/features/research_map/presentation/research_map_state.dart';

void main() {
  testWidgets('PaperScape upload screen renders', (tester) async {
    await tester.pumpWidget(
        MaterialApp(home: ResearchMapScreen(controller: _StubController())));
    expect(find.text('PaperScape'), findsOneWidget);
    expect(find.text('Select PDF'), findsOneWidget);
    expect(find.text('Generate research map'), findsOneWidget);
  });

  testWidgets(
      'narrow ready layout renders long content without overflow and keeps evidence selectable',
      (tester) async {
    final controller = _StubController(
      ResearchMapState(
        phase: WorkflowPhase.ready,
        map: ResearchMap.fromJson({
          'paper_id': 'paper-1',
          'research_question':
              'A very long research question that should still wrap safely on narrow layouts without overflow.',
          'findings': [
            {
              'statement':
                  'A very long finding statement that should wrap across multiple lines on narrow screens without causing any overflow or clipping in the widget tree.',
              'confidence': 'high',
              'evidence': [
                {
                  'chunk_id': 'chunk-1',
                  'page': 1,
                  'excerpt':
                      'A very long evidence excerpt that should remain selectable and wrap correctly even on a narrow test surface.'
                }
              ]
            },
            {
              'statement':
                  'Second long finding statement for stacked rendering.',
              'confidence': 'partial',
              'evidence': [
                {
                  'chunk_id': 'chunk-2',
                  'page': 2,
                  'excerpt':
                      'Second long evidence excerpt for narrow layout verification.'
                }
              ]
            },
            {
              'statement':
                  'Third long finding statement for stacked rendering.',
              'confidence': 'uncertain',
              'evidence': [
                {
                  'chunk_id': 'chunk-3',
                  'page': 3,
                  'excerpt':
                      'Third long evidence excerpt for narrow layout verification.'
                }
              ]
            },
          ],
          'limitations': [
            'A very long limitation that should wrap instead of overflowing at narrow width.'
          ],
          'disclaimer':
              'This AI-generated explanation is grounded in the uploaded document but does not replace expert review.',
        }),
      ),
    );

    await tester.binding.setSurfaceSize(const Size(320, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
        MaterialApp(home: ResearchMapScreen(controller: controller)));

    expect(tester.takeException(), isNull);
    expect(find.textContaining('Finding '), findsNWidgets(3));
    expect(find.byType(SelectableText), findsWidgets);
    expect(find.textContaining('PAGE 1'), findsOneWidget);
    expect(find.text('LIMITATIONS'), findsOneWidget);
  });

  testWidgets('failure and processing controls are discoverable',
      (tester) async {
    final controller = _StubController(
      const ResearchMapState(
        phase: WorkflowPhase.failed,
        errorMessage: 'Something went wrong. Please try again.',
      ),
    );

    await tester.pumpWidget(
        MaterialApp(home: ResearchMapScreen(controller: controller)));
    expect(find.text('Retry'), findsOneWidget);
    expect(find.text('Start over'), findsWidgets);
    expect(find.text('Select PDF'), findsOneWidget);
  });

  testWidgets('processing and failure states expose practical semantics',
      (tester) async {
    final processingController = _StubController(
      const ResearchMapState(
        phase: WorkflowPhase.polling,
        jobStatus: JobStatus.running,
      ),
    );

    await tester.pumpWidget(
        MaterialApp(home: ResearchMapScreen(controller: processingController)));
    expect(find.bySemanticsLabel('Generating grounded findings (running)'),
        findsOneWidget);

    final failureController = _StubController(
      const ResearchMapState(
        phase: WorkflowPhase.failed,
        errorMessage: 'Something went wrong. Please try again.',
      ),
    );
    await tester.pumpWidget(
        MaterialApp(home: ResearchMapScreen(controller: failureController)));
    expect(find.bySemanticsLabel('Workflow failed'), findsOneWidget);
  });
}

class _StubController extends ResearchMapController {
  _StubController([ResearchMapState? initial])
      : super(api: _NoopApi(), picker: _NoopPicker()) {
    if (initial != null) {
      state = initial;
    }
  }
}

class _NoopPicker implements PdfPicker {
  @override
  Future<SelectedPdf?> pickPdf() async => null;
}

class _NoopApi implements PaperScapeApi {
  @override
  Future<JobCreateResponse> createResearchMapJob(String paperId) =>
      throw UnimplementedError();

  @override
  Future<JobStatusResponse> getJobStatus(String jobId) =>
      throw UnimplementedError();

  @override
  Future<ResearchMap> getResearchMap(String paperId) =>
      throw UnimplementedError();

  @override
  Future<UploadResponse> uploadPaper(SelectedPdf pdf) =>
      throw UnimplementedError();
}
