import 'dart:async';
import 'package:flutter/foundation.dart';
import '../../../app/app_config.dart';
import '../data/api_exception.dart';
import '../data/dto/job_response.dart';
import '../data/dto/creator_pack.dart';
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
      this.pollInterval = const Duration(seconds: 2),
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
  int? _pollingGeneration;
  bool _disposed = false;
  int _nextGeneration() {
    _timer?.cancel();
    _timer = null;
    _pollingGeneration = null;
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
    if (state.uploadedPaperId != null) {
      await _createJob(g);
      return;
    }
    try {
      _set(state.copyWith(
          phase: WorkflowPhase.uploading,
          isBusy: true,
          clearError: true,
          clearMap: true,
          clearJob: true));
      final up = await _api.uploadPaper(state.selectedPdf!);
      if (_stale(g)) return;
      if (up.paperId.trim().isEmpty) {
        throw const ApiException(
            code: 'invalid_identifier',
            safeMessage: 'The uploaded paper identifier is invalid.');
      }
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
    final paperId = state.uploadedPaperId;
    if (paperId == null) {
      if (!_stale(g)) {
        _set(state.copyWith(
            phase: WorkflowPhase.failed,
            errorMessage: safeMessageForCode('invalid_identifier'),
            retryAction: RetryAction.upload,
            isBusy: false,
            clearJob: true));
      }
      return;
    }
    try {
      _timer?.cancel();
      _timer = null;
      _pollStarted = null;
      _set(state.copyWith(
          phase: WorkflowPhase.creatingJob,
          isBusy: true,
          clearError: true,
          clearMap: true,
          clearJob: true));
      final job = await _api.createResearchMapJob(paperId);
      if (_stale(g)) return;
      if (job.paperId.trim() != paperId) throw const ParseException();
      _set(state.copyWith(
          phase: WorkflowPhase.polling,
          jobId: job.jobId,
          jobStatus: job.status,
          isBusy: true));
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
    final jobId = state.jobId?.trim();
    if (_pollingGeneration == g || _stale(g)) return;
    if (jobId == null || jobId.isEmpty) {
      _set(state.copyWith(
          phase: WorkflowPhase.failed,
          errorMessage: safeMessageForCode('invalid_identifier'),
          retryAction: RetryAction.createJob,
          isBusy: false,
          clearJob: true));
      return;
    }
    if (_pollStarted != null &&
        _clock().difference(_pollStarted!) >= pollTimeout) {
      _set(state.copyWith(
          phase: WorkflowPhase.failed,
          errorMessage: pollTimeoutMessage,
          retryAction: RetryAction.createJob,
          isBusy: false));
      return;
    }
    _pollingGeneration = g;
    try {
      final js = await _api.getJobStatus(jobId);
      if (_stale(g)) return;
      _set(state.copyWith(
          phase: WorkflowPhase.polling, jobStatus: js.status, isBusy: true));
      if (js.status == JobStatus.pending || js.status == JobStatus.running) {
        _timer = _timerFactory(pollInterval, () => _pollNow(g));
      } else if (js.status == JobStatus.succeeded) {
        await _loadMap(g);
      } else {
        _set(state.copyWith(
            phase: WorkflowPhase.failed,
            errorMessage: safeMessageForCode(js.error),
            retryAction: RetryAction.createJob,
            isBusy: false));
      }
    } on ApiException catch (e) {
      if (!_stale(g)) {
        _set(state.copyWith(
            phase: WorkflowPhase.failed,
            errorMessage: safeMessageForCode(e.code),
            retryAction: RetryAction.createJob,
            isBusy: false));
      }
    } finally {
      if (_pollingGeneration == g) _pollingGeneration = null;
    }
  }

  Future<void> _loadMap(int g) async {
    final paperId = state.uploadedPaperId;
    if (paperId == null) {
      if (!_stale(g)) {
        _set(state.copyWith(
            phase: WorkflowPhase.failed,
            errorMessage: safeMessageForCode('invalid_identifier'),
            retryAction: RetryAction.upload,
            isBusy: false));
      }
      return;
    }
    try {
      _timer?.cancel();
      _set(state.copyWith(phase: WorkflowPhase.loadingMap, isBusy: true));
      final map = await _api.getResearchMap(paperId);
      if (!_stale(g)) {
        _set(state.copyWith(
            phase: WorkflowPhase.ready,
            map: map,
            isBusy: false,
            clearError: true));
      }
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

  Future<void> createCreatorPack(CreatorAudience audience) async {
    final paperId = state.uploadedPaperId;
    if (paperId == null || state.map == null || state.isBusy) return;
    try {
      _set(state.copyWith(isBusy: true, clearError: true));
      final pack = await (_api as CreatorPackApi).createCreatorPack(paperId, audience);
      _set(state.copyWith(creatorPack: pack, isBusy: false));
    } catch (e) {
      _set(state.copyWith(
        isBusy: false,
        errorMessage: e is ApiException ? safeMessageForCode(e.code) : safeMessageForCode(null),
      ));
    }
  }

  Future<void> approveCreatorPack() async {
    final paperId = state.uploadedPaperId;
    final pack = state.creatorPack;
    if (paperId == null || pack == null || state.isBusy) return;
    try {
      _set(state.copyWith(isBusy: true, clearError: true));
      final approved = await (_api as CreatorPackApi).approveCreatorPack(paperId, pack.packId);
      _set(state.copyWith(creatorPack: approved, isBusy: false));
    } catch (e) {
      _set(state.copyWith(
        isBusy: false,
        errorMessage: e is ApiException ? safeMessageForCode(e.code) : safeMessageForCode(null),
      ));
    }
  }

  Future<String?> exportCreatorPack() async {
    final paperId = state.uploadedPaperId;
    final pack = state.creatorPack;
    if (paperId == null || pack == null || pack.status != 'approved') return null;
    try {
      return await (_api as CreatorPackApi).exportCreatorPack(paperId, pack.packId);
    } catch (e) {
      _set(state.copyWith(errorMessage: e is ApiException ? safeMessageForCode(e.code) : safeMessageForCode(null)));
      return null;
    }
  }

  Future<void> retry() {
    if (state.uploadedPaperId != null) {
      return _createJob(state.generation);
    }
    if (state.retryAction == RetryAction.upload) return start();
    return Future<void>.value();
  }

  void reset() {
    final g = _nextGeneration();
    _pollStarted = null;
    _pollingGeneration = null;
    _set(ResearchMapState(generation: g));
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    _pollStarted = null;
    _pollingGeneration = null;
    super.dispose();
  }
}
