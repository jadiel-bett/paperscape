import 'dart:async';
import 'dart:typed_data';

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

class FakePicker implements PdfPicker {
  FakePicker(this.pdf);
  final SelectedPdf pdf;
  @override
  Future<SelectedPdf?> pickPdf() async => pdf;
}

class WorkflowApi implements PaperScapeApi {
  final statuses = <JobStatus>[
    JobStatus.pending,
    JobStatus.running,
    JobStatus.succeeded
  ];
  Uint8List? uploadedBytes;
  String? uploadedFilename;
  String? createdPaperId;
  String? polledJobId;
  int mapRequests = 0;
  int _index = 0;

  @override
  Future<UploadResponse> uploadPaper(SelectedPdf pdf) async {
    uploadedBytes = pdf.bytes;
    uploadedFilename = pdf.filename;
    return const UploadResponse(
        paperId: 'paper-1', filename: 'demo.pdf', pageCount: 1, chunkCount: 3);
  }

  @override
  Future<JobCreateResponse> createResearchMapJob(String paperId) async {
    createdPaperId = paperId;
    return const JobCreateResponse(
        jobId: 'job-1', paperId: 'paper-1', status: JobStatus.pending);
  }

  @override
  Future<JobStatusResponse> getJobStatus(String jobId) async {
    polledJobId = jobId;
    final status = statuses[_index++];
    return JobStatusResponse(
        jobId: 'job-1',
        paperId: 'paper-1',
        status: status,
        createdAt: DateTime.utc(2026),
        updatedAt: DateTime.utc(2026),
        error: null);
  }

  @override
  Future<ResearchMap> getResearchMap(String paperId) async {
    mapRequests++;
    return ResearchMap.fromJson({
      'paper_id': 'paper-1',
      'research_question': 'RQ',
      'findings': [
        {
          'statement': 'F1',
          'confidence': 'high',
          'evidence': [
            {'chunk_id': 'c1', 'page': 1, 'excerpt': 'e1'}
          ]
        },
        {
          'statement': 'F2',
          'confidence': 'partial',
          'evidence': [
            {'chunk_id': 'c2', 'page': 2, 'excerpt': 'e2'}
          ]
        },
        {
          'statement': 'F3',
          'confidence': 'uncertain',
          'evidence': [
            {'chunk_id': 'c3', 'page': 3, 'excerpt': 'e3'}
          ]
        },
      ],
      'limitations': ['L1'],
      'disclaimer':
          'This AI-generated explanation is grounded in the uploaded document but does not replace expert review.',
    });
  }
}

class TestScheduler {
  final callbacks = <void Function()>[];
  Timer schedule(Duration _, void Function() callback) {
    callbacks.add(callback);
    return Timer(Duration.zero, () {});
  }
}

void main() {
  testWidgets('full offline workflow renders ready state', (tester) async {
    final api = WorkflowApi();
    final pdf = SelectedPdf(
        filename: 'demo.pdf',
        bytes: Uint8List.fromList([1, 2, 3]),
        mimeType: 'application/pdf');
    final scheduler = TestScheduler();
    final controller = ResearchMapController(
      api: api,
      picker: FakePicker(pdf),
      timerFactory: scheduler.schedule,
    );

    await tester.pumpWidget(
        MaterialApp(home: ResearchMapScreen(controller: controller)));
    await tester.tap(find.text('Select PDF'));
    await tester.pump();
    await tester.tap(find.text('Generate research map'));
    await tester.pump();
    scheduler.callbacks.removeAt(0)();
    await tester.pump();
    scheduler.callbacks.removeAt(0)();
    await tester.pump();
    await tester.pumpAndSettle();

    expect(api.uploadedBytes, pdf.bytes);
    expect(api.uploadedFilename, 'demo.pdf');
    expect(api.createdPaperId, 'paper-1');
    expect(api.polledJobId, 'job-1');
    expect(api.mapRequests, 1);
    expect(find.text('Research question'), findsOneWidget);
    expect(find.textContaining('Finding '), findsNWidgets(3));
    expect(find.textContaining('Page 1'), findsOneWidget);
    expect(
        find.text(
            'This AI-generated explanation is grounded in the uploaded document but does not replace expert review.'),
        findsOneWidget);
  });
}
