import '../data/dto/job_response.dart';
import '../data/dto/research_map.dart';
import '../data/dto/creator_pack.dart';
import '../data/dto/upload_response.dart';
import '../domain/selected_pdf.dart';

enum WorkflowPhase {
  idle,
  selectingFile,
  fileSelected,
  uploading,
  uploadSucceeded,
  creatingJob,
  polling,
  loadingMap,
  ready,
  failed
}

enum RetryAction { none, upload, createJob, pollJob, loadMap }

class ResearchMapState {
  const ResearchMapState({
    this.phase = WorkflowPhase.idle,
    this.selectedPdf,
    this.selectedMetadata,
    this.validationError,
    this.upload,
    this.jobId,
    this.jobStatus,
    this.map,
    this.creatorPack,
    this.errorMessage,
    this.retryAction = RetryAction.none,
    this.isBusy = false,
    this.generation = 0,
  });
  final WorkflowPhase phase;
  final SelectedPdf? selectedPdf;
  final SelectedPdfMetadata? selectedMetadata;
  final String? validationError;
  final UploadResponse? upload;
  final String? jobId;
  final JobStatus? jobStatus;
  final ResearchMap? map;
  final CreatorPack? creatorPack;
  final String? errorMessage;
  final RetryAction retryAction;
  final bool isBusy;
  final int generation;

  String? get uploadedPaperId {
    final value = upload?.paperId.trim();
    return value == null || value.isEmpty ? null : value;
  }

  ResearchMapState copyWith(
          {WorkflowPhase? phase,
          SelectedPdf? selectedPdf,
          SelectedPdfMetadata? selectedMetadata,
          String? validationError,
          UploadResponse? upload,
          String? jobId,
          JobStatus? jobStatus,
          ResearchMap? map,
          CreatorPack? creatorPack,
          String? errorMessage,
          RetryAction? retryAction,
          bool? isBusy,
          int? generation,
          bool clearPdf = false,
          bool clearUpload = false,
          bool clearJob = false,
          bool clearError = false,
          bool clearMap = false}) =>
      ResearchMapState(
        phase: phase ?? this.phase,
        selectedPdf: clearPdf ? null : selectedPdf ?? this.selectedPdf,
        selectedMetadata:
            clearPdf ? null : selectedMetadata ?? this.selectedMetadata,
        validationError:
            clearError ? null : validationError ?? this.validationError,
        upload: clearUpload ? null : upload ?? this.upload,
        jobId: clearJob ? null : jobId ?? this.jobId,
        jobStatus: clearJob ? null : jobStatus ?? this.jobStatus,
        map: clearMap ? null : map ?? this.map,
        creatorPack: clearMap ? null : creatorPack ?? this.creatorPack,
        errorMessage: clearError ? null : errorMessage ?? this.errorMessage,
        retryAction: retryAction ?? this.retryAction,
        isBusy: isBusy ?? this.isBusy,
        generation: generation ?? this.generation,
      );
}
