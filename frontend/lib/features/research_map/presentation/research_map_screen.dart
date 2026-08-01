import 'package:flutter/material.dart';

import '../../../app/app_theme.dart';
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

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.controller.state;
    return Scaffold(
      body: Stack(
        children: [
          const Positioned.fill(
            child: IgnorePointer(
                child: CustomPaint(painter: _AtlasBackdropPainter())),
          ),
          SafeArea(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final compact = constraints.maxWidth < 700;
                return SingleChildScrollView(
                  padding: EdgeInsets.fromLTRB(
                    compact ? 18 : 32,
                    compact ? 18 : 28,
                    compact ? 18 : 32,
                    48,
                  ),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 1200),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          _AtlasHeader(compact: compact),
                          const SizedBox(height: 28),
                          _IntroBlock(state: state, compact: compact),
                          const SizedBox(height: 22),
                          _UploadPanel(
                            state: state,
                            onPick: widget.controller.selectPdf,
                            onStart: widget.controller.start,
                            onReset: widget.controller.reset,
                          ),
                          const SizedBox(height: 18),
                          if (state.upload != null) _DocumentRail(state: state),
                          if (_processing(state.phase)) ...[
                            const SizedBox(height: 18),
                            _Processing(
                                phase: state.phase,
                                status: state.jobStatus?.name),
                          ],
                          if (state.phase == WorkflowPhase.failed) ...[
                            const SizedBox(height: 18),
                            _Failure(
                              message: state.errorMessage ??
                                  'Something went wrong. Please try again.',
                              onRetry: widget.controller.retry,
                              onReset: widget.controller.reset,
                            ),
                          ],
                          if (state.phase == WorkflowPhase.ready &&
                              state.map != null) ...[
                            const SizedBox(height: 30),
                            _MapView(map: state.map!),
                          ],
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  bool _processing(WorkflowPhase phase) => {
        WorkflowPhase.uploading,
        WorkflowPhase.creatingJob,
        WorkflowPhase.polling,
        WorkflowPhase.loadingMap,
      }.contains(phase);
}

class _AtlasHeader extends StatelessWidget {
  const _AtlasHeader({required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) => Row(
        children: [
          const _PaperScapeMark(),
          const SizedBox(width: 12),
          Text(
            'PaperScape',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  fontSize: compact ? 19 : 22,
                  letterSpacing: -0.5,
                ),
          ),
          const Spacer(),
          if (!compact)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(.72),
                borderRadius: BorderRadius.circular(999),
                border: Border.all(color: const Color(0xFFDCE4EF)),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.auto_awesome, size: 15, color: paperScapeViolet),
                  SizedBox(width: 7),
                  Text(
                    'Powered by watsonx.ai + Granite',
                    style: TextStyle(
                      color: paperScapeInk,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
        ],
      );
}

class _PaperScapeMark extends StatelessWidget {
  const _PaperScapeMark();

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 34,
        height: 34,
        child: CustomPaint(painter: _PaperMarkPainter()),
      );
}

class _IntroBlock extends StatelessWidget {
  const _IntroBlock({required this.state, required this.compact});

  final ResearchMapState state;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final hasResult = state.phase == WorkflowPhase.ready && state.map != null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          hasResult
              ? 'RESEARCH ATLAS / MAP READY'
              : 'EVIDENCE-BACKED RESEARCH STUDIO',
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: paperScapeBlue,
                letterSpacing: 1.5,
              ),
        ),
        const SizedBox(height: 10),
        ConstrainedBox(
          constraints: BoxConstraints(maxWidth: compact ? 520 : 700),
          child: Text(
            hasResult
                ? 'A clear trail from every finding back to the paper.'
                : 'Turn dense papers into clear, traceable stories.',
            style: Theme.of(context).textTheme.displaySmall?.copyWith(
                  fontSize: compact ? 36 : 48,
                ),
          ),
        ),
        const SizedBox(height: 12),
        ConstrainedBox(
          constraints: BoxConstraints(maxWidth: compact ? 560 : 650),
          child: Text(
            hasResult
                ? 'Review the question, findings, limitations, and SourceTrail evidence before you share the story.'
                : 'Upload one research PDF and PaperScape will map the question, findings, limitations, and source trail.',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: paperScapeMutedInk,
                  fontSize: compact ? 15 : 17,
                ),
          ),
        ),
        if (!hasResult) ...[
          const SizedBox(height: 16),
          const Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _TrustPill(icon: Icons.layers_outlined, label: 'Page-aware'),
              _TrustPill(icon: Icons.route_outlined, label: 'Evidence-linked'),
              _TrustPill(
                  icon: Icons.visibility_outlined, label: 'Human-reviewed'),
            ],
          ),
        ],
      ],
    );
  }
}

class _TrustPill extends StatelessWidget {
  const _TrustPill({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(.72),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: const Color(0xFFDCE4EF)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: paperScapeBlue),
            const SizedBox(width: 7),
            Text(label, style: Theme.of(context).textTheme.labelLarge),
          ],
        ),
      );
}

class _UploadPanel extends StatelessWidget {
  const _UploadPanel({
    required this.state,
    required this.onPick,
    required this.onStart,
    required this.onReset,
  });

  final ResearchMapState state;
  final VoidCallback onPick;
  final VoidCallback onStart;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) {
    final meta = state.selectedMetadata;
    final hasFile = meta != null;
    final isBusy = state.isBusy;
    return Semantics(
      label: 'PDF upload controls',
      child: Card(
        clipBehavior: Clip.antiAlias,
        child: Container(
          padding: const EdgeInsets.all(24),
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              colors: [Colors.white, Color(0xFFF3F7FF)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final narrow = constraints.maxWidth < 650;
              final copy = Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '01 / START WITH A PAPER',
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                          color: paperScapeViolet,
                          letterSpacing: 1.3,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Select one PDF',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 7),
                  Text(
                    'Keep the source close. Your map will keep every major claim tied to its page.',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ],
              );
              final action = Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  InkWell(
                    onTap: isBusy ? null : onPick,
                    borderRadius: BorderRadius.circular(18),
                    child: Container(
                      constraints: const BoxConstraints(minHeight: 116),
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(
                        color: hasFile ? const Color(0xFFEFF4FF) : Colors.white,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(
                          color: hasFile
                              ? paperScapeBlue
                              : const Color(0xFFB8C8DD),
                          width: hasFile ? 1.5 : 1,
                        ),
                      ),
                      child: Row(
                        children: [
                          _PdfGlyph(selected: hasFile),
                          const SizedBox(width: 14),
                          Expanded(
                            child: hasFile
                                ? Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Text(
                                        meta.filename,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleMedium,
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        '${humanFileSize(meta.sizeBytes)}  •  PDF ready to map',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodyMedium,
                                      ),
                                    ],
                                  )
                                : Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Text(
                                        'Choose a research paper',
                                        style: Theme.of(context)
                                            .textTheme
                                            .titleMedium,
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        'PDF only  •  click to browse files',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodyMedium,
                                      ),
                                    ],
                                  ),
                          ),
                          Icon(
                            hasFile ? Icons.check_circle : Icons.arrow_forward,
                            color: hasFile
                                ? const Color(0xFF16803C)
                                : paperScapeBlue,
                          ),
                        ],
                      ),
                    ),
                  ),
                  if (state.validationError != null) ...[
                    const SizedBox(height: 9),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.error_outline,
                            size: 17,
                            color: Theme.of(context).colorScheme.error),
                        const SizedBox(width: 7),
                        Expanded(
                          child: Text(
                            state.validationError!,
                            style: TextStyle(
                                color: Theme.of(context).colorScheme.error),
                          ),
                        ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 10,
                    runSpacing: 8,
                    children: [
                      OutlinedButton.icon(
                        onPressed: isBusy ? null : onPick,
                        icon: const Icon(Icons.upload_file_outlined, size: 18),
                        label: Text(hasFile ? 'Replace file' : 'Select PDF'),
                      ),
                      FilledButton.icon(
                        onPressed: (!isBusy &&
                                hasFile &&
                                state.validationError == null)
                            ? onStart
                            : null,
                        icon: const Icon(Icons.auto_awesome, size: 18),
                        label: const Text('Generate research map'),
                      ),
                      if (state.phase != WorkflowPhase.idle)
                        TextButton(
                          onPressed: onReset,
                          child: const Text('Start over'),
                        ),
                    ],
                  ),
                ],
              );

              return narrow
                  ? Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [copy, const SizedBox(height: 20), action],
                    )
                  : Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(child: copy),
                        const SizedBox(width: 32),
                        Expanded(flex: 2, child: action),
                      ],
                    );
            },
          ),
        ),
      ),
    );
  }
}

class _PdfGlyph extends StatelessWidget {
  const _PdfGlyph({required this.selected});

  final bool selected;

  @override
  Widget build(BuildContext context) => Container(
        width: 48,
        height: 58,
        decoration: BoxDecoration(
          color: selected ? paperScapeBlue : const Color(0xFFE8EEFA),
          borderRadius: BorderRadius.circular(11),
        ),
        child: Icon(
          Icons.description_outlined,
          color: selected ? Colors.white : paperScapeBlue,
          size: 27,
        ),
      );
}

class _DocumentRail extends StatelessWidget {
  const _DocumentRail({required this.state});

  final ResearchMapState state;

  @override
  Widget build(BuildContext context) {
    final upload = state.upload!;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      decoration: BoxDecoration(
        color: paperScapeInk,
        borderRadius: BorderRadius.circular(16),
        boxShadow: const [
          BoxShadow(
              color: Color(0x1607111F), blurRadius: 18, offset: Offset(0, 8))
        ],
      ),
      child: Wrap(
        spacing: 20,
        runSpacing: 9,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.insert_drive_file_outlined,
                  size: 17, color: paperScapeCyan),
              const SizedBox(width: 8),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 300),
                child: Text(
                  upload.filename,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
          _RailStat(label: 'PAGES', value: '${upload.pageCount}'),
          _RailStat(label: 'CHUNKS', value: '${upload.chunkCount}'),
          const Text(
            'SOURCE LOCKED',
            style: TextStyle(
                color: Color(0xFF9EB2CD),
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1),
          ),
        ],
      ),
    );
  }
}

class _RailStat extends StatelessWidget {
  const _RailStat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(value,
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.w700)),
          const SizedBox(width: 5),
          Text(label,
              style: const TextStyle(
                  color: Color(0xFF9EB2CD),
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1)),
        ],
      );
}

class _Processing extends StatelessWidget {
  const _Processing({required this.phase, this.status});

  final WorkflowPhase phase;
  final String? status;

  @override
  Widget build(BuildContext context) {
    final current = switch (phase) {
      WorkflowPhase.uploading => 0,
      WorkflowPhase.creatingJob => 1,
      WorkflowPhase.polling => 2,
      WorkflowPhase.loadingMap => 3,
      _ => 0,
    };
    final title = switch (phase) {
      WorkflowPhase.uploading => 'Uploading & extracting',
      WorkflowPhase.creatingJob => 'Preparing the research map',
      WorkflowPhase.polling =>
        'Grounding findings${status == null ? '' : ' · $status'}',
      WorkflowPhase.loadingMap => 'Assembling your atlas',
      _ => 'Processing',
    };
    const labels = ['Upload', 'Structure', 'Evidence', 'Map'];
    final semanticsTitle =
        'Generating grounded findings${status == null ? '' : ' ($status)'}';
    return Semantics(
      label: semanticsTitle,
      liveRegion: true,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(22),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      color: const Color(0xFFE9E3FF),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(Icons.route_outlined,
                        color: paperScapeViolet, size: 20),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                      child: Text(title,
                          style: Theme.of(context).textTheme.titleMedium)),
                  const SizedBox(width: 12),
                  const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2.5)),
                ],
              ),
              const SizedBox(height: 22),
              LayoutBuilder(
                builder: (context, constraints) => Row(
                  children: List.generate(labels.length, (index) {
                    final active = index == current;
                    final complete = index < current;
                    return Expanded(
                      child: Row(
                        children: [
                          Container(
                            width: 27,
                            height: 27,
                            decoration: BoxDecoration(
                              color: complete
                                  ? const Color(0xFFDDF5E5)
                                  : active
                                      ? paperScapeBlue
                                      : const Color(0xFFE9EEF7),
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              complete ? Icons.check : Icons.circle,
                              size: complete ? 16 : 9,
                              color: complete
                                  ? const Color(0xFF16803C)
                                  : active
                                      ? Colors.white
                                      : const Color(0xFF8B9AB0),
                            ),
                          ),
                          const SizedBox(width: 7),
                          Flexible(
                            child: Text(
                              labels[index],
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: active || complete
                                    ? paperScapeInk
                                    : paperScapeMutedInk,
                                fontSize: 12,
                                fontWeight: active || complete
                                    ? FontWeight.w700
                                    : FontWeight.w500,
                              ),
                            ),
                          ),
                          if (index < labels.length - 1)
                            Expanded(
                              child: Container(
                                height: 2,
                                margin:
                                    const EdgeInsets.symmetric(horizontal: 8),
                                color: index < current
                                    ? const Color(0xFFB9E6C7)
                                    : const Color(0xFFE0E6EF),
                              ),
                            ),
                        ],
                      ),
                    );
                  }),
                ),
              ),
              const SizedBox(height: 14),
              Text(
                  'PaperScape is following the evidence trail. No fake percentages are shown.',
                  style: Theme.of(context).textTheme.bodyMedium),
            ],
          ),
        ),
      ),
    );
  }
}

class _Failure extends StatelessWidget {
  const _Failure(
      {required this.message, required this.onRetry, required this.onReset});

  final String message;
  final VoidCallback onRetry;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) => Semantics(
        label: 'Workflow failed',
        child: Card(
          color: const Color(0xFFFFF3F0),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                      color: const Color(0xFFFFDAD4),
                      borderRadius: BorderRadius.circular(12)),
                  child: const Icon(Icons.priority_high_rounded,
                      color: Color(0xFFB42318)),
                ),
                const SizedBox(width: 13),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('The trail broke before the map was ready',
                          style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 5),
                      Text(message),
                      const SizedBox(height: 13),
                      Wrap(
                        spacing: 8,
                        children: [
                          FilledButton(
                              onPressed: onRetry, child: const Text('Retry')),
                          TextButton(
                              onPressed: onReset,
                              child: const Text('Start over')),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      );
}

class _MapView extends StatelessWidget {
  const _MapView({required this.map});

  final ResearchMap map;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            color: paperScapeInk,
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('RESEARCH QUESTION',
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                          color: paperScapeCyan, letterSpacing: 1.4)),
                  const SizedBox(height: 10),
                  SelectableText(
                    map.researchQuestion,
                    style: Theme.of(context)
                        .textTheme
                        .headlineSmall
                        ?.copyWith(color: Colors.white, height: 1.25),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),
          Wrap(
            spacing: 12,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text('THE FINDINGS',
                  style: Theme.of(context)
                      .textTheme
                      .labelMedium
                      ?.copyWith(color: paperScapeBlue, letterSpacing: 1.4)),
              Text('${map.findings.length} TRACEABLE CLAIMS',
                  style: Theme.of(context).textTheme.labelMedium),
            ],
          ),
          const SizedBox(height: 12),
          ...map.findings.asMap().entries.map((entry) => Padding(
                padding: const EdgeInsets.only(bottom: 14),
                child: _FindingCard(index: entry.key + 1, finding: entry.value),
              )),
          _LimitationsPanel(limitations: map.limitations),
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFFE9EEF7),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFFD4DEEB)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.shield_outlined,
                    color: paperScapeBlue, size: 20),
                const SizedBox(width: 10),
                Expanded(
                    child: SelectableText(map.disclaimer,
                        style: Theme.of(context)
                            .textTheme
                            .bodyMedium
                            ?.copyWith(color: paperScapeInk))),
              ],
            ),
          ),
        ],
      );
}

class _FindingCard extends StatelessWidget {
  const _FindingCard({required this.index, required this.finding});

  final int index;
  final Finding finding;

  @override
  Widget build(BuildContext context) {
    final confidence = finding.confidence.name;
    final accent = switch (confidence) {
      'high' => const Color(0xFF16803C),
      'partial' => const Color(0xFFB25E09),
      _ => paperScapeViolet,
    };
    final confidenceIcon = switch (confidence) {
      'high' => Icons.verified_outlined,
      'partial' => Icons.remove_circle_outline,
      _ => Icons.help_outline,
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            LayoutBuilder(
              builder: (context, constraints) {
                final number = Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      index.toString().padLeft(2, '0'),
                      style: const TextStyle(
                          color: paperScapeBlue,
                          fontSize: 25,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -1),
                    ),
                    Text('Finding $index',
                        style: Theme.of(context)
                            .textTheme
                            .labelMedium
                            ?.copyWith(
                                color: paperScapeMutedInk,
                                fontSize: 9,
                                letterSpacing: .4)),
                  ],
                );
                final badge = Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
                  decoration: BoxDecoration(
                      color: accent.withOpacity(.1),
                      borderRadius: BorderRadius.circular(10)),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(confidenceIcon, size: 15, color: accent),
                      const SizedBox(width: 5),
                      Text(confidence,
                          style: TextStyle(
                              color: accent,
                              fontSize: 11,
                              fontWeight: FontWeight.w800)),
                    ],
                  ),
                );
                final statement = SelectableText(finding.statement,
                    style: Theme.of(context).textTheme.titleLarge);

                if (constraints.maxWidth < 480) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [number, const Spacer(), badge]),
                      const SizedBox(height: 14),
                      statement,
                    ],
                  );
                }
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    number,
                    const SizedBox(width: 14),
                    Expanded(child: statement),
                    const SizedBox(width: 12),
                    badge,
                  ],
                );
              },
            ),
            const SizedBox(height: 17),
            ...finding.evidence
                .map((evidence) => _EvidenceBlock(evidence: evidence)),
          ],
        ),
      ),
    );
  }
}

class _EvidenceBlock extends StatelessWidget {
  const _EvidenceBlock({required this.evidence});

  final Evidence evidence;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        margin: const EdgeInsets.only(top: 8),
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
        decoration: BoxDecoration(
          color: const Color(0xFFF6F9FD),
          borderRadius: BorderRadius.circular(14),
          border:
              const Border(left: BorderSide(color: paperScapeCyan, width: 3)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
                  decoration: BoxDecoration(
                      color: const Color(0xFFDDF7FC),
                      borderRadius: BorderRadius.circular(7)),
                  child: Text('PAGE ${evidence.page}',
                      style: const TextStyle(
                          color: Color(0xFF087F8C),
                          fontSize: 10,
                          fontWeight: FontWeight.w800,
                          letterSpacing: .7)),
                ),
                const SizedBox(width: 9),
                Text(evidence.chunkId,
                    style: const TextStyle(
                        color: paperScapeMutedInk,
                        fontFamily: 'monospace',
                        fontSize: 11,
                        fontWeight: FontWeight.w600)),
                const Spacer(),
                const Icon(Icons.link, size: 15, color: paperScapeBlue),
              ],
            ),
            const SizedBox(height: 9),
            SelectableText(
              '“${evidence.excerpt}”',
              style: Theme.of(context)
                  .textTheme
                  .bodyLarge
                  ?.copyWith(color: paperScapeInk, fontSize: 15),
            ),
          ],
        ),
      );
}

class _LimitationsPanel extends StatelessWidget {
  const _LimitationsPanel({required this.limitations});

  final List<String> limitations;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(19),
        decoration: BoxDecoration(
          color: const Color(0xFFFFF8E6),
          borderRadius: BorderRadius.circular(17),
          border: Border.all(color: const Color(0xFFF3D58C)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.warning_amber_rounded,
                    color: Color(0xFF9B5C00), size: 21),
                const SizedBox(width: 8),
                Text('LIMITATIONS',
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: const Color(0xFF9B5C00), letterSpacing: 1.2)),
              ],
            ),
            const SizedBox(height: 10),
            ...limitations.map((limitation) => Padding(
                  padding: const EdgeInsets.only(bottom: 5),
                  child: SelectableText('• $limitation',
                      style: Theme.of(context)
                          .textTheme
                          .bodyMedium
                          ?.copyWith(color: paperScapeInk)),
                )),
          ],
        ),
      );
}

class _AtlasBackdropPainter extends CustomPainter {
  const _AtlasBackdropPainter();

  @override
  void paint(Canvas canvas, Size size) {
    if (!size.width.isFinite || !size.height.isFinite) return;
    final contour = Paint()
      ..color = const Color(0xFFB8C8DD).withOpacity(.24)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    final glow = Paint()..color = paperScapeBlue.withOpacity(.1);
    final points = <Offset>[
      Offset(size.width * .08, size.height * .13),
      Offset(size.width * .23, size.height * .08),
      Offset(size.width * .46, size.height * .17),
      Offset(size.width * .73, size.height * .09),
      Offset(size.width * .91, size.height * .2),
      Offset(size.width * .14, size.height * .74),
      Offset(size.width * .54, size.height * .65),
      Offset(size.width * .84, size.height * .78),
    ];
    for (var i = 0; i < points.length; i++) {
      canvas.drawCircle(points[i], i.isEven ? 5 : 3, glow);
      canvas.drawCircle(points[i], i.isEven ? 2 : 1.5,
          Paint()..color = paperScapeBlue.withOpacity(.25));
    }
    for (var i = 0; i < points.length - 1; i++) {
      final path = Path()..moveTo(points[i].dx, points[i].dy);
      final middle =
          Offset((points[i].dx + points[i + 1].dx) / 2, points[i].dy - 30);
      path.quadraticBezierTo(
          middle.dx, middle.dy, points[i + 1].dx, points[i + 1].dy);
      canvas.drawPath(path, contour);
    }
    final arc = Path()
      ..moveTo(size.width * .72, 0)
      ..cubicTo(size.width * .9, size.height * .12, size.width * .62,
          size.height * .27, size.width * .86, size.height * .4)
      ..cubicTo(size.width * .98, size.height * .48, size.width * .75,
          size.height * .58, size.width, size.height * .66);
    canvas.drawPath(arc, contour);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _PaperMarkPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final back = Paint()..color = paperScapeViolet;
    final mid = Paint()..color = paperScapeCyan;
    final front = Paint()..color = paperScapeBlue;
    canvas.save();
    canvas.rotate(-.08);
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            const Rect.fromLTWH(6, 4, 22, 25), const Radius.circular(4)),
        back);
    canvas.restore();
    canvas.save();
    canvas.rotate(.08);
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            const Rect.fromLTWH(4, 7, 23, 25), const Radius.circular(4)),
        mid);
    canvas.restore();
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            const Rect.fromLTWH(3, 5, 24, 26), const Radius.circular(4)),
        front);
    final line = Paint()
      ..color = Colors.white
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(const Offset(9, 13), const Offset(21, 13), line);
    canvas.drawLine(const Offset(9, 18), const Offset(18, 18), line);
    canvas.drawLine(const Offset(9, 23), const Offset(15, 23), line);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
