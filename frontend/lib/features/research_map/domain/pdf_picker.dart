import 'package:file_picker/file_picker.dart';

import 'selected_pdf.dart';

abstract interface class PdfPicker {
  Future<SelectedPdf?> pickPdf();
}

class FilePickerPdfPicker implements PdfPicker {
  const FilePickerPdfPicker();

  @override
  Future<SelectedPdf?> pickPdf() async {
    final result = await FilePicker.pickFiles(
      allowMultiple: false,
      type: FileType.custom,
      allowedExtensions: const ['pdf'],
      withData: true,
    );
    if (result == null || result.files.isEmpty) return null;
    final file = result.files.single;
    final bytes = file.bytes;
    if (bytes == null) return null;
    return SelectedPdf(
      filename: file.name,
      bytes: bytes,
      mimeType: 'application/pdf',
    );
  }
}
