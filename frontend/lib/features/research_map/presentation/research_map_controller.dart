import 'dart:async';
import 'package:flutter/foundation.dart';
import '../../../app/app_config.dart';
import '../data/api_exception.dart';
import '../data/dto/job_response.dart';
import '../data/paperscape_api_client.dart';
import '../domain/pdf_picker.dart';
import '../domain/selected_pdf.dart';
import 'research_map_state.dart';

typedef TimerFactory = Timer Function(
    Duration duration, void Function() callback);
typedef Clock = DateTime Function();

const pollTimeoutMessage =
    'PaperScape took too long to finish generating the research map. Please retry.';

class ResearchMapController extends ChangeNotifier {
  ResearchMapController(
      {required PaperScapeApi api,
      required PdfPicker picker,
      AppConfig? config,
      TimerFactory? timerFactory,
      Clock? clock,
      this.pollInterval = const Duration(milliseconds: 1500),
      this.pollTimeout = const Duration(minutes: 2)})
      : _api = api,
        _picker = picker,
        _config = config ?? AppConfig(),
        _timerFactory = timerFactory ?? Timer.new,
        _clock = clock ?? DateTime.now;
  final PaperScapeApi _api;
  final PdfPicker _picker;
  final AppConfig _config;
  final TimerFactory _timerFactory;
  final Clock _clock;
  final Duration pollInterval;
  final Duration pollTimeout;
  ResearchMapState state = const ResearchMapState();
  Timer? _timer;
  DateTime? _pollStarted;
  bool _polling = false;
  bool _disposed = false;
  int _nextGeneration() {
    _timer?.cancel();
    return state.generation + 1;
  }

  void _set(ResearchMapState s) {
    if (_disposed) return;
    state = s;
    notifyListeners();
  }

  bool _stale(int g) => _disposed || g != state.generation;

  Future<void> selectPdf() async {
    final g = _nextGeneration();
    _set(ResearchMapState(
        phase: WorkflowPhase.selectingFile, generation: g, isBusy: true));
    SelectedPdf? pdf;
    try {
      pdf = await _picker.pickPdf();
    } catch (_) {
      if (!_stale(g)) {
        _set(ResearchMapState(
            phase: WorkflowPhase.failed,
            errorMessage: safeMessageForCode(null),
            retryAction: RetryAction.none,
            generation: g));
      }
      return;
    }
    if (_stale(g)) return;
    if (pdf == null) {
      _set(ResearchMapState(generation: g));
      return;
    }
    final err =
        validateSelectedPdf(pdf, maxBytes: _config.clientMaxUploadBytes);
    _set(ResearchMapState(
        phase: WorkflowPhase.fileSelected,
        selectedPdf: pdf,
        selectedMetadata: pdf.metadata,
        validationError: err,
        generation: g));
  }

  Future<void> start() async {
    if (state.isBusy ||
        state.selectedPdf == null ||
        state.validationError != null) return;
    final g = state.generation;
    try {
      _set(state.copyWith(
          phase: WorkflowPhase.uploading,
          isBusy: true,
          clearError: true,
          clearMap: true));
      final up = await _api.uploadPaper(state.selectedPdf!);
      if (_stale(g)) return;
      _set(state.copyWith(
          phase: WorkflowPhase.uploadSucceeded, upload: up, isBusy: false));
      await _createJob(g);
    } catch (e) {
      if (!_stale(g)) {
        _set(state.copyWith(
            phase: WorkflowPhase.failed,
            errorMessage: e is ApiException
                ? safeMessageForCode(e.code)
                : safeMessageForCode(null),
            retryAction: RetryAction.upload,
            isBusy: false));
      }
    }
  }

  Future<void> _createJob(int g) async {
    if (state.upload == null) return;
    try {
      _set(state.copyWith(
          phase: WorkflowPhase.creatingJob, isBusy: true, clearError: true));
      final job = await _api.createResearchMapJob(state.upload!.paperId);
      if (_stale(g)) return;
      _set(state.copyWith(
          phase: WorkflowPhase.polling,
          jobId: job.jobId,
          jobStatus: job.status,
          isBusy: false));
      _pollStarted = _clock();
      await _pollNow(g);
    } catch (e) {
      if (!_stale(g)) {
        _set(state.copyWith(
            phase: WorkflowPhase.failed,
            errorMessage: e is ApiException
                ? safeMessageForCode(e.code)
                : safeMessageForCode(null),
            retryAction: RetryAction.createJob,
            isBusy: false));
      }
    }
  }

  Future<void> _pollNow(int g) async {
    if (_polling || state.jobId == null || _stale(g)) return;
    if (_pollStarted != null &&
        _clock().difference(_pollStarted!) >= pollTimeout) {
      _set(state.copyWith(
          phase: WorkflowPhase.failed,
          errorMessage: pollTimeoutMessage,
          retryAction: RetryAction.pollJob));
      return;
    }
    _polling = true;
    try {
      final js = await _api.getJobStatus(state.jobId!);
      if (_stale(g)) return;
      _set(state.copyWith(phase: WorkflowPhase.polling, jobStatus: js.status));
      if (js.status == JobStatus.pending || js.status == JobStatus.running) {
        _timer = _timerFactory(pollInterval, () => _pollNow(g));
      } else if (js.status == JobStatus.succeeded) {
        await _loadMap(g);
      } else {
        _set(state.copyWith(
            phase: WorkflowPhase.failed,
            errorMessage: safeMessageForCode(js.error),
            retryAction: RetryAction.createJob));
      }
    } on ApiException catch (e) {
      if (!_stale(g)) {
        _set(state.copyWith(
            phase: WorkflowPhase.failed,
            errorMessage: safeMessageForCode(e.code),
            retryAction: RetryAction.pollJob));
      }
    } finally {
      _polling = false;
    }
  }

  Future<void> _loadMap(int g) async {
    if (state.upload == null) return;
    try {
      _timer?.cancel();
      _set(state.copyWith(phase: WorkflowPhase.loadingMap, isBusy: true));
      final map = await _api.getResearchMap(state.upload!.paperId);
      if (!_stale(g)) {
        _set(state.copyWith(
            phase: WorkflowPhase.ready, map: map, isBusy: false));
      }
    } catch (e) {
      if (!_stale(g)) {
        _set(state.copyWith(
            phase: WorkflowPhase.failed,
            errorMessage: e is ApiException
                ? safeMessageForCode(e.code)
                : safeMessageForCode(null),
            retryAction: RetryAction.loadMap,
            isBusy: false));
      }
    }
  }

  Future<void> retry() {
    switch (state.retryAction) {
      case RetryAction.upload:
        return start();
      case RetryAction.createJob:
        return _createJob(state.generation);
      case RetryAction.pollJob:
        _pollStarted = _clock();
        return _pollNow(state.generation);
      case RetryAction.loadMap:
        return _loadMap(state.generation);
      case RetryAction.none:
        return Future<void>.value();
    }
  }

  void reset() {
    final g = _nextGeneration();
    _pollStarted = null;
    _set(ResearchMapState(generation: g));
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    _pollStarted = null;
    super.dispose();
  }
}
