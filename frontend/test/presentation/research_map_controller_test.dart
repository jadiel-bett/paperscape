import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/app/app_config.dart';
import 'package:frontend/features/research_map/data/api_exception.dart';
import 'package:frontend/features/research_map/data/dto/job_response.dart';
import 'package:frontend/features/research_map/data/dto/research_map.dart';
import 'package:frontend/features/research_map/data/dto/upload_response.dart';
import 'package:frontend/features/research_map/data/paperscape_api_client.dart';
import 'package:frontend/features/research_map/domain/pdf_picker.dart';
import 'package:frontend/features/research_map/domain/selected_pdf.dart';
import 'package:frontend/features/research_map/presentation/research_map_controller.dart';
import 'package:frontend/features/research_map/presentation/research_map_state.dart';

const _disclaimer =
    'This AI-generated explanation is grounded in the uploaded document but does not replace expert review.';

class FakePicker implements PdfPicker {
  FakePicker(this.result);
  SelectedPdf? result;
  @override
  Future<SelectedPdf?> pickPdf() async => result;
}

class TestScheduler {
  final callbacks = <void Function()>[];
  final timers = <Timer>[];
  Timer schedule(Duration _, void Function() callback) {
    late final Timer timer;
    timer = Timer(const Duration(days: 1), () {});
    timers.add(timer);
    callbacks.add(() {
      timer.cancel();
      callback();
    });
    return timer;
  }

  void cancelAll() {
    for (final timer in timers) {
      timer.cancel();
    }
  }

  void fireNext() {
    final callback = callbacks.removeAt(0);
    callback();
  }

  void fireCallback(void Function() callback) {
    callback();
  }
}

class FakeClock {
  FakeClock(this.now);
  DateTime now;

  DateTime call() => now;

  void advance(Duration duration) {
    now = now.add(duration);
  }
}

class ControlledApi implements PaperScapeApi {
  ControlledApi();

  final uploadCompleter = Completer<UploadResponse>();
  final createJobCompleters = <Completer<JobCreateResponse>>[];
  final mapCompleters = <Completer<ResearchMap>>[];
  final pollCompleters = <Completer<JobStatusResponse>>[];
  int createJobCalls = 0;
  int pollCalls = 0;
  int mapCalls = 0;
  String? createdPaperId;
  final polledJobIds = <String>[];
  final mappedPaperIds = <String>[];
  int activePollCalls = 0;

  @override
  Future<UploadResponse> uploadPaper(SelectedPdf pdf) => uploadCompleter.future;

  @override
  Future<JobCreateResponse> createResearchMapJob(String paperId) {
    createJobCalls++;
    createdPaperId = paperId;
    final completer = Completer<JobCreateResponse>();
    createJobCompleters.add(completer);
    return completer.future;
  }

  @override
  Future<JobStatusResponse> getJobStatus(String jobId) {
    pollCalls++;
    polledJobIds.add(jobId);
    activePollCalls++;
    final completer = Completer<JobStatusResponse>();
    pollCompleters.add(completer);
    return completer.future.whenComplete(() => activePollCalls--);
  }

  @override
  Future<ResearchMap> getResearchMap(String paperId) {
    mapCalls++;
    mappedPaperIds.add(paperId);
    final completer = Completer<ResearchMap>();
    mapCompleters.add(completer);
    return completer.future;
  }
}

Future<Completer<T>> waitForCompleter<T>(List<Completer<T>> completers,
    {int index = 0}) async {
  for (var attempt = 0; attempt < 10; attempt++) {
    if (completers.length > index) return completers[index];
    await Future<void>.value();
  }
  throw StateError('Controlled operation was not registered.');
}

class ThrowingPicker implements PdfPicker {
  @override
  Future<SelectedPdf?> pickPdf() =>
      Future<SelectedPdf?>.error(StateError('browser path sensitive sentinel'));
}

class DelayedCreateApi extends FakeApi {
  DelayedCreateApi({required super.statuses});
  final Completer<JobCreateResponse> completer = Completer<JobCreateResponse>();

  @override
  Future<JobCreateResponse> createResearchMapJob(String paperId) {
    createJobCalls++;
    lastPaperId = paperId;
    return completer.future;
  }
}

class MalformedUploadApi extends FakeApi {
  MalformedUploadApi() : super(statuses: [JobStatus.pending]);

  @override
  Future<UploadResponse> uploadPaper(SelectedPdf pdf) async =>
      const UploadResponse(
          paperId: '   ', filename: 'demo.pdf', pageCount: 1, chunkCount: 1);
}

class FakeApi implements PaperScapeApi {
  FakeApi(
      {required this.statuses,
      this.throwOnPoll = false,
      this.throwOnMap = false});
  final List<JobStatus> statuses;
  final bool throwOnPoll;
  final bool throwOnMap;
  int createJobCalls = 0;
  int mapCalls = 0;
  String? lastPaperId;
  int _pollIndex = 0;

  @override
  Future<JobCreateResponse> createResearchMapJob(String paperId) async {
    createJobCalls++;
    lastPaperId = paperId;
    return const JobCreateResponse(
        jobId: 'job-1', paperId: 'paper-1', status: JobStatus.pending);
  }

  @override
  Future<JobStatusResponse> getJobStatus(String jobId) async {
    if (throwOnPoll) {
      throw const ApiException(code: 'internal_error', safeMessage: 'secret');
    }
    final status = statuses[_pollIndex++];
    return JobStatusResponse(
      jobId: 'job-1',
      paperId: 'paper-1',
      status: status,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: status == JobStatus.failed ? 'map_generation_failed' : null,
    );
  }

  @override
  Future<ResearchMap> getResearchMap(String paperId) async {
    mapCalls++;
    if (throwOnMap) {
      throw const ApiException(code: 'map_not_found', safeMessage: 'secret');
    }
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
            {'chunk_id': 'c2', 'page': 1, 'excerpt': 'e2'}
          ]
        },
        {
          'statement': 'F3',
          'confidence': 'uncertain',
          'evidence': [
            {'chunk_id': 'c3', 'page': 1, 'excerpt': 'e3'}
          ]
        },
      ],
      'limitations': ['L1'],
      'disclaimer': _disclaimer,
    });
  }

  @override
  Future<UploadResponse> uploadPaper(SelectedPdf pdf) async {
    return const UploadResponse(
        paperId: 'paper-1', filename: 'demo.pdf', pageCount: 1, chunkCount: 3);
  }
}

SelectedPdf samplePdf() => SelectedPdf(
    filename: 'demo.PDF',
    bytes: Uint8List.fromList([1, 2, 3]),
    mimeType: 'application/pdf');

void main() {
  test('initial state is idle', () {
    final controller = ResearchMapController(
        api: FakeApi(statuses: [JobStatus.succeeded]),
        picker: FakePicker(samplePdf()));
    expect(controller.state.phase, WorkflowPhase.idle);
  });

  test('picker cancellation returns to safe state', () async {
    final controller = ResearchMapController(
        api: FakeApi(statuses: [JobStatus.succeeded]),
        picker: FakePicker(null));
    await controller.selectPdf();
    expect(controller.state.phase, WorkflowPhase.idle);
  });

  test('invalid file is rejected before upload', () async {
    final controller = ResearchMapController(
      api: FakeApi(statuses: [JobStatus.succeeded]),
      picker: FakePicker(SelectedPdf(
          filename: 'bad.txt',
          bytes: Uint8List.fromList([1]),
          mimeType: 'text/plain')),
      config: AppConfig(clientMaxUploadBytes: 10),
    );
    await controller.selectPdf();
    expect(controller.state.validationError, isNotNull);
  });

  test('duplicate start ignored and job creation uses uploaded paper id',
      () async {
    final api = DelayedCreateApi(statuses: [JobStatus.failed]);
    final scheduler = TestScheduler();
    final controller = ResearchMapController(
      api: api,
      picker: FakePicker(samplePdf()),
      timerFactory: scheduler.schedule,
    );
    await controller.selectPdf();
    final first = controller.start();
    final second = controller.start();
    api.completer.complete(const JobCreateResponse(
        jobId: 'job-1', paperId: 'paper-1', status: JobStatus.pending));
    await first;
    await second;
    expect(api.lastPaperId, 'paper-1');
    expect(api.createJobCalls, 1);
    expect(controller.state.upload?.paperId, 'paper-1');
  });

  test('pending then running then succeeded loads map once', () async {
    final api = FakeApi(
        statuses: [JobStatus.pending, JobStatus.running, JobStatus.succeeded]);
    final scheduler = TestScheduler();
    final controller = ResearchMapController(
      api: api,
      picker: FakePicker(samplePdf()),
      timerFactory: scheduler.schedule,
    );

    await controller.selectPdf();
    await controller.start();
    expect(controller.state.phase, WorkflowPhase.polling);
    scheduler.fireNext();
    await Future<void>.value();
    scheduler.fireNext();
    await Future<void>.value();
    await Future<void>.value();

    expect(controller.state.phase, WorkflowPhase.ready);
    expect(api.mapCalls, 1);
  });

  test('failed terminal job shows safe error and clears loading state',
      () async {
    final api = FakeApi(statuses: [JobStatus.failed]);
    final controller =
        ResearchMapController(api: api, picker: FakePicker(samplePdf()));

    await controller.selectPdf();
    await controller.start();

    expect(controller.state.phase, WorkflowPhase.failed);
    expect(controller.state.errorMessage,
        safeMessageForCode('map_generation_failed'));
    expect(controller.state.isBusy, isFalse);
    expect(controller.state.map, isNull);
  });

  test('poll and map failures retry by creating a new job', () async {
    final pollApi = FakeApi(statuses: [JobStatus.pending], throwOnPoll: true);
    final controller =
        ResearchMapController(api: pollApi, picker: FakePicker(samplePdf()));
    await controller.selectPdf();
    await controller.start();
    expect(controller.state.retryAction, RetryAction.createJob);
    final pollCreateCalls = pollApi.createJobCalls;
    await controller.retry();
    expect(pollApi.createJobCalls, pollCreateCalls + 1);

    final mapApi = FakeApi(
        statuses: [JobStatus.succeeded, JobStatus.succeeded], throwOnMap: true);
    final controller2 =
        ResearchMapController(api: mapApi, picker: FakePicker(samplePdf()));
    await controller2.selectPdf();
    await controller2.start();
    expect(controller2.state.retryAction, RetryAction.createJob);
    final callsBefore = mapApi.createJobCalls;
    await controller2.retry();
    expect(mapApi.createJobCalls, callsBefore + 1);
  });

  test('malformed uploaded paper id fails locally without creating a job',
      () async {
    final api = MalformedUploadApi();
    final controller =
        ResearchMapController(api: api, picker: FakePicker(samplePdf()));

    await controller.selectPdf();
    await controller.start();

    expect(api.createJobCalls, 0);
    expect(controller.state.phase, WorkflowPhase.failed);
    expect(controller.state.errorMessage,
        safeMessageForCode('invalid_identifier'));
    expect(controller.state.isBusy, isFalse);
  });

  test('reset clears file and results', () async {
    final controller = ResearchMapController(
        api: FakeApi(statuses: [JobStatus.succeeded]),
        picker: FakePicker(samplePdf()));
    await controller.selectPdf();
    controller.reset();
    expect(controller.state.selectedPdf, isNull);
    expect(controller.state.upload, isNull);
    expect(controller.state.map, isNull);
  });

  test('stale upload completion is ignored after selecting a newer pdf',
      () async {
    final api = ControlledApi();
    final picker = FakePicker(samplePdf());
    final controller = ResearchMapController(api: api, picker: picker);

    await controller.selectPdf();
    final uploadA = controller.start();

    picker.result = SelectedPdf(
      filename: 'newer.pdf',
      bytes: Uint8List.fromList([9, 9, 9]),
      mimeType: 'application/pdf',
    );
    await controller.selectPdf();

    api.uploadCompleter.complete(const UploadResponse(
      paperId: 'old-paper',
      filename: 'old.pdf',
      pageCount: 1,
      chunkCount: 1,
    ));
    await uploadA;

    expect(controller.state.selectedMetadata?.filename, 'newer.pdf');
    expect(controller.state.upload, isNull);
    expect(controller.state.phase, WorkflowPhase.fileSelected);
    expect(api.createJobCalls, 0);
  });

  test('stale job creation completion is ignored after reset', () async {
    final api = ControlledApi();
    final controller = ResearchMapController(
      api: api,
      picker: FakePicker(samplePdf()),
    );

    await controller.selectPdf();
    final future = controller.start();
    api.uploadCompleter.complete(const UploadResponse(
      paperId: 'paper-1',
      filename: 'demo.pdf',
      pageCount: 1,
      chunkCount: 1,
    ));
    final createJob = await waitForCompleter(api.createJobCompleters);
    controller.reset();
    createJob.complete(const JobCreateResponse(
      jobId: 'old-job',
      paperId: 'paper-1',
      status: JobStatus.pending,
    ));
    await future;

    expect(controller.state.jobId, isNull);
    expect(controller.state.phase, WorkflowPhase.idle);
    expect(api.pollCalls, 0);
  });

  test('stale poll completion cannot alter newer workflow or load map',
      () async {
    final api = ControlledApi();
    final picker = FakePicker(samplePdf());
    final controller = ResearchMapController(api: api, picker: picker);

    await controller.selectPdf();
    final future = controller.start();
    api.uploadCompleter.complete(const UploadResponse(
      paperId: 'paper-1',
      filename: 'demo.pdf',
      pageCount: 1,
      chunkCount: 1,
    ));
    final createJob = await waitForCompleter(api.createJobCompleters);
    createJob.complete(const JobCreateResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.pending,
    ));
    final poll = await waitForCompleter(api.pollCompleters);

    picker.result = SelectedPdf(
      filename: 'workflow-b.pdf',
      bytes: Uint8List.fromList([7, 7, 7]),
      mimeType: 'application/pdf',
    );
    await controller.selectPdf();

    poll.complete(JobStatusResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.succeeded,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: null,
    ));
    await future;

    expect(controller.state.selectedMetadata?.filename, 'workflow-b.pdf');
    expect(controller.state.phase, WorkflowPhase.fileSelected);
    expect(api.mapCalls, 0);
  });

  test('stale map completion is ignored after reset', () async {
    final api = ControlledApi();
    final controller = ResearchMapController(
      api: api,
      picker: FakePicker(samplePdf()),
    );

    await controller.selectPdf();
    final future = controller.start();
    api.uploadCompleter.complete(const UploadResponse(
      paperId: 'paper-1',
      filename: 'demo.pdf',
      pageCount: 1,
      chunkCount: 1,
    ));
    final createJob = await waitForCompleter(api.createJobCompleters);
    createJob.complete(const JobCreateResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.pending,
    ));
    final poll = await waitForCompleter(api.pollCompleters);
    poll.complete(JobStatusResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.succeeded,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: null,
    ));
    final map = await waitForCompleter(api.mapCompleters);
    controller.reset();
    map.complete(ResearchMap.fromJson({
      'paper_id': 'paper-1',
      'research_question': 'Old map',
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
            {'chunk_id': 'c2', 'page': 1, 'excerpt': 'e2'}
          ]
        },
        {
          'statement': 'F3',
          'confidence': 'uncertain',
          'evidence': [
            {'chunk_id': 'c3', 'page': 1, 'excerpt': 'e3'}
          ]
        },
      ],
      'limitations': ['L1'],
      'disclaimer': _disclaimer,
    }));
    await future;

    expect(controller.state.map, isNull);
    expect(controller.state.phase, WorkflowPhase.idle);
  });

  test('dispose prevents later notifications from in-flight completions',
      () async {
    final api = ControlledApi();
    final controller = ResearchMapController(
      api: api,
      picker: FakePicker(samplePdf()),
    );
    var notifications = 0;
    controller.addListener(() {
      notifications++;
    });

    await controller.selectPdf();
    final future = controller.start();
    controller.dispose();
    api.uploadCompleter.complete(const UploadResponse(
      paperId: 'paper-1',
      filename: 'demo.pdf',
      pageCount: 1,
      chunkCount: 1,
    ));
    await future;

    expect(notifications, greaterThanOrEqualTo(1));
  });

  test('timeout stops polling deterministically and retry creates a new job',
      () async {
    final api = FakeApi(statuses: [JobStatus.pending, JobStatus.pending]);
    final scheduler = TestScheduler();
    final clock = FakeClock(DateTime.utc(2026, 1, 1));
    final controller = ResearchMapController(
      api: api,
      picker: FakePicker(samplePdf()),
      timerFactory: scheduler.schedule,
      clock: clock.call,
      pollTimeout: const Duration(seconds: 5),
    );

    await controller.selectPdf();
    await controller.start();
    expect(controller.state.jobId, 'job-1');
    expect(controller.state.phase, WorkflowPhase.polling);
    expect(scheduler.callbacks, hasLength(1));

    clock.advance(const Duration(seconds: 5));
    scheduler.fireNext();
    await Future<void>.value();

    expect(controller.state.phase, WorkflowPhase.failed);
    expect(controller.state.errorMessage, pollTimeoutMessage);
    expect(controller.state.retryAction, RetryAction.createJob);
    expect(api.createJobCalls, 1);
    expect(scheduler.callbacks, isEmpty);

    await controller.retry();
    expect(controller.state.phase, WorkflowPhase.polling);
    expect(api.createJobCalls, 2);
  });

  test('poll overlap guard prevents concurrent poll requests', () async {
    final api = ControlledApi();
    final scheduler = TestScheduler();
    final controller = ResearchMapController(
      api: api,
      picker: FakePicker(samplePdf()),
      timerFactory: scheduler.schedule,
    );

    await controller.selectPdf();
    final startFuture = controller.start();
    api.uploadCompleter.complete(const UploadResponse(
      paperId: 'paper-1',
      filename: 'demo.pdf',
      pageCount: 1,
      chunkCount: 1,
    ));
    final createJob = await waitForCompleter(api.createJobCompleters);
    createJob.complete(const JobCreateResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.pending,
    ));
    await Future<void>.value();

    expect(api.pollCalls, 1);
    expect(api.activePollCalls, 1);
    api.pollCompleters.first.complete(JobStatusResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.pending,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: null,
    ));
    await Future<void>.value();
    expect(scheduler.callbacks, hasLength(1));

    final scheduled = scheduler.callbacks.first;
    scheduled();
    expect(api.pollCalls, 2);
    expect(api.activePollCalls, 1);

    scheduled();
    expect(api.pollCalls, 2);
    expect(api.activePollCalls, 1);

    api.pollCompleters[1].complete(JobStatusResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.pending,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: null,
    ));
    await Future<void>.value();
    expect(scheduler.callbacks.length, greaterThanOrEqualTo(1));

    scheduler.fireNext();
    expect(api.pollCalls, 3);
    api.pollCompleters[2].complete(JobStatusResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.failed,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: 'map_generation_failed',
    ));
    await startFuture;
  });

  test('failed job retry creates a new backend job and polls the new job id',
      () async {
    final api = ControlledApi();
    final controller =
        ResearchMapController(api: api, picker: FakePicker(samplePdf()));

    await controller.selectPdf();
    final firstRun = controller.start();
    api.uploadCompleter.complete(const UploadResponse(
      paperId: 'paper-1',
      filename: 'demo.pdf',
      pageCount: 1,
      chunkCount: 1,
    ));
    final createJob = await waitForCompleter(api.createJobCompleters);
    createJob.complete(const JobCreateResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.pending,
    ));
    await Future<void>.value();
    api.pollCompleters.first.complete(JobStatusResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.failed,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: 'map_generation_failed',
    ));
    await firstRun;

    expect(controller.state.retryAction, RetryAction.createJob);
    expect(controller.state.jobId, 'job-a');

    final secondRun = controller.retry();
    await Future<void>.value();
    api.createJobCompleters[1].complete(const JobCreateResponse(
      jobId: 'job-b',
      paperId: 'paper-1',
      status: JobStatus.pending,
    ));
    await Future<void>.value();
    api.pollCompleters[1].complete(JobStatusResponse(
      jobId: 'job-b',
      paperId: 'paper-1',
      status: JobStatus.failed,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: 'map_generation_failed',
    ));
    await secondRun;

    expect(api.createdPaperId, 'paper-1');
    expect(api.createJobCalls, 2);
    expect(api.polledJobIds, contains('job-b'));
    expect(api.polledJobIds.last, 'job-b');
  });

  test('map-load retry clears old error and creates a new job for same paper',
      () async {
    final api = ControlledApi();
    final controller =
        ResearchMapController(api: api, picker: FakePicker(samplePdf()));

    await controller.selectPdf();
    final startFuture = controller.start();
    api.uploadCompleter.complete(const UploadResponse(
      paperId: 'paper-1',
      filename: 'demo.pdf',
      pageCount: 1,
      chunkCount: 1,
    ));
    final createJob = await waitForCompleter(api.createJobCompleters);
    createJob.complete(const JobCreateResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.pending,
    ));
    await Future<void>.value();
    api.pollCompleters.first.complete(JobStatusResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.succeeded,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: null,
    ));
    await Future<void>.value();
    final firstMap = await waitForCompleter(api.mapCompleters);
    firstMap.completeError(
      const ApiException(code: 'map_not_found', safeMessage: 'secret'),
    );
    await startFuture;

    final createCalls = api.createJobCalls;
    final pollCalls = api.pollCalls;
    expect(controller.state.retryAction, RetryAction.createJob);
    expect(controller.state.errorMessage, isNotNull);

    final retryFuture = controller.retry();
    final secondCreate =
        await waitForCompleter(api.createJobCompleters, index: 1);
    expect(controller.state.phase, WorkflowPhase.creatingJob);
    expect(controller.state.errorMessage, isNull);
    expect(controller.state.jobId, isNull);
    secondCreate.complete(const JobCreateResponse(
      jobId: 'job-b',
      paperId: 'paper-1',
      status: JobStatus.pending,
    ));
    final secondPoll = await waitForCompleter(api.pollCompleters, index: 1);
    secondPoll.complete(JobStatusResponse(
      jobId: 'job-b',
      paperId: 'paper-1',
      status: JobStatus.succeeded,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: null,
    ));
    final secondMap = await waitForCompleter(api.mapCompleters, index: 1);
    secondMap.complete(ResearchMap.fromJson({
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
            {'chunk_id': 'c2', 'page': 1, 'excerpt': 'e2'}
          ]
        },
        {
          'statement': 'F3',
          'confidence': 'uncertain',
          'evidence': [
            {'chunk_id': 'c3', 'page': 1, 'excerpt': 'e3'}
          ]
        },
      ],
      'limitations': ['L1'],
      'disclaimer': _disclaimer,
    }));
    await retryFuture;

    expect(api.mappedPaperIds.every((paperId) => paperId == 'paper-1'), isTrue);
    expect(api.createJobCalls, createCalls + 1);
    expect(api.pollCalls, pollCalls + 1);
    expect(api.polledJobIds.last, 'job-b');
    expect(controller.state.phase, WorkflowPhase.ready);
    expect(controller.state.errorMessage, isNull);
    expect(controller.state.isBusy, isFalse);
  });

  test('reset clears workflow state and ignores in-flight completions',
      () async {
    final api = ControlledApi();
    final scheduler = TestScheduler();
    final controller = ResearchMapController(
      api: api,
      picker: FakePicker(samplePdf()),
      timerFactory: scheduler.schedule,
    );

    await controller.selectPdf();
    final future = controller.start();
    api.uploadCompleter.complete(const UploadResponse(
      paperId: 'paper-1',
      filename: 'demo.pdf',
      pageCount: 1,
      chunkCount: 1,
    ));
    final createJob = await waitForCompleter(api.createJobCompleters);
    createJob.complete(const JobCreateResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.pending,
    ));
    await Future<void>.value();
    controller.reset();

    expect(controller.state.phase, WorkflowPhase.idle);
    expect(controller.state.selectedPdf, isNull);
    expect(controller.state.upload, isNull);
    expect(controller.state.jobId, isNull);
    expect(controller.state.jobStatus, isNull);
    expect(controller.state.map, isNull);
    expect(controller.state.errorMessage, isNull);
    expect(controller.state.retryAction, RetryAction.none);
    expect(controller.state.isBusy, isFalse);

    api.pollCompleters.first.complete(JobStatusResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.succeeded,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: null,
    ));
    await future;
    expect(controller.state.phase, WorkflowPhase.idle);
    expect(api.mapCalls, 0);
  });

  test(
      'dispose cancels polling callbacks and in-flight completions do not notify',
      () async {
    final api = ControlledApi();
    final scheduler = TestScheduler();
    final controller = ResearchMapController(
      api: api,
      picker: FakePicker(samplePdf()),
      timerFactory: scheduler.schedule,
    );
    var notifications = 0;
    controller.addListener(() {
      notifications++;
    });

    await controller.selectPdf();
    final future = controller.start();
    api.uploadCompleter.complete(const UploadResponse(
      paperId: 'paper-1',
      filename: 'demo.pdf',
      pageCount: 1,
      chunkCount: 1,
    ));
    final createJob = await waitForCompleter(api.createJobCompleters);
    createJob.complete(const JobCreateResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.pending,
    ));
    await Future<void>.value();
    final beforeDisposeCalls = api.pollCalls;
    final notificationsBeforeDispose = notifications;
    controller.dispose();

    if (scheduler.callbacks.isNotEmpty) {
      scheduler.callbacks.first();
    }
    expect(api.pollCalls, beforeDisposeCalls);

    api.pollCompleters.first.complete(JobStatusResponse(
      jobId: 'job-a',
      paperId: 'paper-1',
      status: JobStatus.failed,
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      error: 'map_generation_failed',
    ));
    await future;
    expect(notifications, notificationsBeforeDispose);
  });
}
