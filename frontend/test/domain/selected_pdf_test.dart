import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/features/research_map/domain/selected_pdf.dart';

SelectedPdf pdf(
        {String name = 'a.pdf',
        String? mime = 'application/pdf',
        int size = 1}) =>
    SelectedPdf(filename: name, mimeType: mime, bytes: Uint8List(size));
void main() {
  test('selected PDF validation covers boundaries', () {
    expect(validateSelectedPdf(pdf(), maxBytes: 1), isNull);
    expect(validateSelectedPdf(pdf(name: 'A.PDF'), maxBytes: 1), isNull);
    expect(validateSelectedPdf(pdf(name: '   '), maxBytes: 1), isNotNull);
    expect(validateSelectedPdf(pdf(name: 'a.txt'), maxBytes: 1), isNotNull);
    expect(
        validateSelectedPdf(pdf(mime: 'text/plain'), maxBytes: 1), isNotNull);
    expect(validateSelectedPdf(pdf(mime: null), maxBytes: 1), isNull);
    expect(validateSelectedPdf(pdf(size: 0), maxBytes: 1), isNotNull);
    expect(validateSelectedPdf(pdf(size: 2), maxBytes: 1), isNotNull);
  });
}
