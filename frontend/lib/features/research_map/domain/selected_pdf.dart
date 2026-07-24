import 'dart:typed_data';

class SelectedPdf {
  const SelectedPdf({
    required this.filename,
    required this.bytes,
    this.mimeType,
  });

  final String filename;
  final Uint8List bytes;
  final String? mimeType;

  int get sizeBytes => bytes.length;

  SelectedPdfMetadata get metadata => SelectedPdfMetadata(
        filename: filename,
        sizeBytes: sizeBytes,
        mimeType: mimeType,
      );
}

class SelectedPdfMetadata {
  const SelectedPdfMetadata({
    required this.filename,
    required this.sizeBytes,
    this.mimeType,
  });

  final String filename;
  final int sizeBytes;
  final String? mimeType;
}

String? validateSelectedPdf(SelectedPdf pdf, {required int maxBytes}) {
  final filename = pdf.filename.trim();
  if (filename.isEmpty) return 'Choose a PDF with a filename.';
  if (!filename.toLowerCase().endsWith('.pdf')) {
    return 'Choose a file ending in .pdf.';
  }
  final mime = pdf.mimeType?.trim().toLowerCase();
  if (mime != null && mime.isNotEmpty && mime != 'application/pdf') {
    return 'Choose a PDF file.';
  }
  if (pdf.bytes.isEmpty) return 'Choose a non-empty PDF file.';
  if (pdf.bytes.length > maxBytes) return 'Choose a smaller PDF file.';
  return null;
}

String humanFileSize(int bytes) {
  if (bytes < 1024) return '$bytes B';
  final kb = bytes / 1024;
  if (kb < 1024) return '${kb.toStringAsFixed(1)} KB';
  return '${(kb / 1024).toStringAsFixed(1)} MB';
}
