import 'package:flutter/material.dart';
import '../data/dto/research_map.dart';
import '../domain/selected_pdf.dart';
import 'research_map_controller.dart';
import 'research_map_state.dart';

class ResearchMapScreen extends StatefulWidget {
  const ResearchMapScreen({super.key, required this.controller});
  final ResearchMapController controller;
  @override
  State<ResearchMapScreen> createState() => _ResearchMapScreenState();
}

class _ResearchMapScreenState extends State<ResearchMapScreen> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_changed);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    super.dispose();
  }

  void _changed() => setState(() {});
  @override
  Widget build(BuildContext context) {
    final s = widget.controller.state;
    return Scaffold(
        body: SafeArea(
            child: Center(
                child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 980),
                    child:
                        ListView(padding: const EdgeInsets.all(20), children: [
                      Text('PaperScape',
                          style: Theme.of(context).textTheme.displaySmall),
                      const SizedBox(height: 8),
                      const Text(
                          'Upload a paper. Build an evidence-backed research map.'),
                      const SizedBox(height: 24),
                      _UploadPanel(
                          state: s,
                          onPick: widget.controller.selectPdf,
                          onStart: widget.controller.start,
                          onReset: widget.controller.reset),
                      const SizedBox(height: 16),
                      if (s.upload != null)
                        Card(
                            child: ListTile(
                                title: Text(s.upload!.filename),
                                subtitle: Text(
                                    '${s.upload!.pageCount} pages • ${s.upload!.chunkCount} chunks'))),
                      if (_processing(s.phase))
                        _Processing(phase: s.phase, status: s.jobStatus?.name),
                      if (s.phase == WorkflowPhase.failed)
                        _Failure(
                            message: s.errorMessage ??
                                'Something went wrong. Please try again.',
                            onRetry: widget.controller.retry,
                            onReset: widget.controller.reset),
                      if (s.phase == WorkflowPhase.ready && s.map != null)
                        _MapView(map: s.map!),
                    ])))));
  }

  bool _processing(WorkflowPhase p) => {
        WorkflowPhase.uploading,
        WorkflowPhase.creatingJob,
        WorkflowPhase.polling,
        WorkflowPhase.loadingMap
      }.contains(p);
}

class _UploadPanel extends StatelessWidget {
  const _UploadPanel(
      {required this.state,
      required this.onPick,
      required this.onStart,
      required this.onReset});
  final ResearchMapState state;
  final VoidCallback onPick, onStart, onReset;
  @override
  Widget build(BuildContext context) {
    final meta = state.selectedMetadata;
    return Semantics(
        label: 'PDF upload controls',
        child: Card(
            child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Select one PDF',
                          style: Theme.of(context).textTheme.titleLarge),
                      const SizedBox(height: 12),
                      if (meta != null)
                        Text(
                            '${meta.filename} • ${humanFileSize(meta.sizeBytes)}'),
                      if (state.validationError != null)
                        Text(state.validationError!,
                            style: TextStyle(
                                color: Theme.of(context).colorScheme.error)),
                      const SizedBox(height: 12),
                      Wrap(spacing: 12, runSpacing: 8, children: [
                        OutlinedButton(
                            onPressed: state.isBusy ? null : onPick,
                            child: Text(
                                meta == null ? 'Select PDF' : 'Replace file')),
                        FilledButton(
                            onPressed: (!state.isBusy &&
                                    meta != null &&
                                    state.validationError == null)
                                ? onStart
                                : null,
                            child: const Text('Generate research map')),
                        TextButton(
                            onPressed: state.isBusy ? null : onReset,
                            child: const Text('Start over'))
                      ])
                    ]))));
  }
}

class _Processing extends StatelessWidget {
  const _Processing({required this.phase, this.status});
  final WorkflowPhase phase;
  final String? status;
  @override
  Widget build(BuildContext context) {
    final text = switch (phase) {
      WorkflowPhase.uploading => 'Uploading paper',
      WorkflowPhase.creatingJob => 'Creating research-map job',
      WorkflowPhase.polling =>
        'Generating grounded findings${status == null ? '' : ' ($status)'}',
      WorkflowPhase.loadingMap => 'Loading research map',
      _ => 'Processing'
    };
    return Semantics(
        label: text,
        liveRegion: true,
        child: Card(
            child: ListTile(
                leading: const CircularProgressIndicator(),
                title: Text(text),
                subtitle: const Text('No fake percentages are shown.'))));
  }
}

class _Failure extends StatelessWidget {
  const _Failure(
      {required this.message, required this.onRetry, required this.onReset});
  final String message;
  final VoidCallback onRetry, onReset;
  @override
  Widget build(BuildContext context) => Semantics(
      label: 'Workflow failed',
      child: Card(
          color: Theme.of(context).colorScheme.errorContainer,
          child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(message),
                    const SizedBox(height: 8),
                    Wrap(spacing: 8, children: [
                      FilledButton(
                          onPressed: onRetry, child: const Text('Retry')),
                      TextButton(
                          onPressed: onReset, child: const Text('Start over'))
                    ])
                  ]))));
}

class _MapView extends StatelessWidget {
  const _MapView({required this.map});
  final ResearchMap map;
  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Research question',
            style: Theme.of(context).textTheme.titleLarge),
        SelectableText(map.researchQuestion),
        const SizedBox(height: 12),
        ...map.findings
            .asMap()
            .entries
            .map((e) => _FindingCard(index: e.key + 1, finding: e.value)),
        Card(
            child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Limitations',
                          style: Theme.of(context).textTheme.titleMedium),
                      ...map.limitations.map((l) => SelectableText('• $l'))
                    ]))),
        Card(
            child: Padding(
                padding: const EdgeInsets.all(16),
                child: SelectableText(map.disclaimer)))
      ]);
}

class _FindingCard extends StatelessWidget {
  const _FindingCard({required this.index, required this.finding});
  final int index;
  final Finding finding;
  @override
  Widget build(BuildContext context) => Card(
      child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Finding $index',
                style: Theme.of(context).textTheme.titleMedium),
            SelectableText(finding.statement),
            Chip(label: Text('Confidence: ${finding.confidence.name}')),
            ...finding.evidence.map((ev) => Container(
                width: double.infinity,
                margin: const EdgeInsets.only(top: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                    border: Border.all(
                        color: Theme.of(context).colorScheme.outlineVariant),
                    borderRadius: BorderRadius.circular(8)),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Page ${ev.page} • ${ev.chunkId}',
                          style: Theme.of(context).textTheme.labelMedium),
                      SelectableText(ev.excerpt)
                    ])))
          ])));
}
