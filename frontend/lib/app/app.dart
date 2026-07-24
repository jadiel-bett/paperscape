import 'package:flutter/material.dart';
import 'app_config.dart';
import 'app_theme.dart';
import '../features/research_map/data/paperscape_api_client.dart';
import '../features/research_map/domain/pdf_picker.dart';
import '../features/research_map/presentation/research_map_controller.dart';
import '../features/research_map/presentation/research_map_screen.dart';

class PaperScapeApp extends StatefulWidget {
  const PaperScapeApp({super.key});
  @override
  State<PaperScapeApp> createState() => _PaperScapeAppState();
}

class _PaperScapeAppState extends State<PaperScapeApp> {
  late final ResearchMapController controller;
  @override
  void initState() {
    super.initState();
    final config = AppConfig();
    controller = ResearchMapController(
        api: PaperScapeApiClient(baseUrl: config.apiBaseUrl),
        picker: const FilePickerPdfPicker(),
        config: config);
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
      title: 'PaperScape',
      theme: buildPaperScapeTheme(),
      home: ResearchMapScreen(controller: controller));
}
