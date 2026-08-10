import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:frontend/features/research_map/data/api_exception.dart';
import 'package:frontend/features/research_map/data/paperscape_api_client.dart';
import 'package:frontend/features/research_map/domain/selected_pdf.dart';

class CapturingSender implements MultipartSender {
  CapturingSender(this.response);
  final http.StreamedResponse response;
  http.MultipartRequest? request;

  @override
  Future<http.StreamedResponse> send(http.MultipartRequest request) async {
    this.request = request;
    return response;
  }
}

class FakeClient extends http.BaseClient {
  FakeClient({required this.body, this.statusCode = 200});
  final String body;
  final int statusCode;
  Uri? lastUri;
  String? method;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    lastUri = request.url;
    method = request.method;
    return http.StreamedResponse(Stream.value(utf8.encode(body)), statusCode);
  }
}

class HangingClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      Completer<http.StreamedResponse>().future;
}

void main() {
  test('upload timeout allows slow document extraction', () {
    final client = PaperScapeApiClient(baseUrl: 'http://host/api/v1');

    expect(client.uploadTimeout,
        greaterThanOrEqualTo(const Duration(seconds: 90)));
    client.close();
  });

  test('upload request is inspectable and exact', () async {
    final sender = CapturingSender(
      http.StreamedResponse(
        Stream.value(utf8.encode(
            '{"paper_id":"p","filename":"a.pdf","page_count":1,"chunk_count":2}')),
        201,
      ),
    );
    final client = PaperScapeApiClient(
      baseUrl: 'http://localhost:8000/api/v1/',
      multipartSender: sender,
    );

    final bytes = Uint8List.fromList([37, 80, 68, 70]);
    await client.uploadPaper(
      SelectedPdf(filename: 'a.pdf', bytes: bytes, mimeType: 'application/pdf'),
    );

    final request = sender.request!;
    expect(request.method, 'POST');
    expect(request.url.path, '/api/v1/papers');
    expect(request.files, hasLength(1));
    expect(request.files.single.field, 'file');
    expect(request.files.single.filename, 'a.pdf');
    expect(request.files.single.contentType.toString(), 'application/pdf');
    expect(await request.files.single.finalize().toBytes(), bytes);
    expect(request.fields, isEmpty);
  });

  test('route identifiers remain safe path segments', () async {
    final client = FakeClient(
      body:
          '{"job_id":"job-1","paper_id":"paper-1","status":"pending","created_at":"2026-01-01T00:00:00Z"}',
      statusCode: 202,
    );
    final api =
        PaperScapeApiClient(baseUrl: 'http://host/api/v1', client: client);

    final created =
        await api.createResearchMapJob('123e4567-e89b-12d3-a456-426614174000');
    expect(client.method, 'POST');
    expect(client.lastUri!.pathSegments, [
      'api',
      'v1',
      'papers',
      '123e4567-e89b-12d3-a456-426614174000',
      'research-map-jobs'
    ]);
    expect(client.lastUri!.query, isEmpty);
    expect(client.lastUri!.fragment, isEmpty);
    expect(created.jobId, 'job-1');
    expect(created.paperId, 'paper-1');
    expect(created.createdAt, DateTime.utc(2026));

    await api.createResearchMapJob('paper id/with spaces');
    expect(client.method, 'POST');
    expect(client.lastUri!.pathSegments,
        ['api', 'v1', 'papers', 'paper id/with spaces', 'research-map-jobs']);
    expect(client.lastUri!.path,
        '/api/v1/papers/paper%20id%2Fwith%20spaces/research-map-jobs');
    expect(client.lastUri!.query, isEmpty);
    expect(client.lastUri!.fragment, isEmpty);

    final client2 = FakeClient(
        body:
            '{"job_id":"j","paper_id":"p","status":"pending","created_at":"2026-01-01T00:00:00+00:00","updated_at":"2026-01-01T00:00:01+00:00","error":null}');
    final api2 =
        PaperScapeApiClient(baseUrl: 'http://host/api/v1', client: client2);
    await api2.getJobStatus('job?query');
    expect(client2.method, 'GET');
    expect(client2.lastUri!.pathSegments, ['api', 'v1', 'jobs', 'job?query']);
    expect(client2.lastUri!.query, isEmpty);
    expect(client2.lastUri!.fragment, isEmpty);

    const mapBody =
        '{"paper_id":"p","research_question":"rq","findings":[{"statement":"s1","confidence":"high","evidence":[{"chunk_id":"c1","page":1,"excerpt":"e1"}]},{"statement":"s2","confidence":"partial","evidence":[{"chunk_id":"c2","page":1,"excerpt":"e2"}]},{"statement":"s3","confidence":"uncertain","evidence":[{"chunk_id":"c3","page":1,"excerpt":"e3"}]}],"limitations":["l1"],"disclaimer":"This AI-generated explanation is grounded in the uploaded document but does not replace expert review."}';
    final mapClient = FakeClient(body: mapBody);
    final mapApi =
        PaperScapeApiClient(baseUrl: 'http://host/api/v1', client: mapClient);
    await mapApi.getResearchMap('paper#fragment');
    expect(mapClient.lastUri!.pathSegments,
        ['api', 'v1', 'papers', 'paper#fragment', 'research-map']);
    expect(mapClient.lastUri!.query, isEmpty);
    expect(mapClient.lastUri!.fragment, isEmpty);

    final client3 = FakeClient(
        body:
            '{"paper_id":"p","research_question":"rq","findings":[{"statement":"s1","confidence":"high","evidence":[{"chunk_id":"c1","page":1,"excerpt":"e1"}]},{"statement":"s2","confidence":"partial","evidence":[{"chunk_id":"c2","page":1,"excerpt":"e2"}]},{"statement":"s3","confidence":"uncertain","evidence":[{"chunk_id":"c3","page":1,"excerpt":"e3"}]}],"limitations":["l1"],"disclaimer":"This AI-generated explanation is grounded in the uploaded document but does not replace expert review."}');
    final api3 =
        PaperScapeApiClient(baseUrl: 'http://host/api/v1', client: client3);
    await api3.getResearchMap('paper%value');
    expect(client3.lastUri!.pathSegments,
        ['api', 'v1', 'papers', 'paper%value', 'research-map']);
    expect(client3.lastUri!.path, '/api/v1/papers/paper%25value/research-map');
    expect(client3.lastUri!.query, isEmpty);
    expect(client3.lastUri!.fragment, isEmpty);

    await api3.getResearchMap('paper%2Fvalue');
    expect(client3.lastUri!.pathSegments,
        ['api', 'v1', 'papers', 'paper%2Fvalue', 'research-map']);
    expect(
        client3.lastUri!.path, '/api/v1/papers/paper%252Fvalue/research-map');
  });

  test('html error and timeout are sanitized', () async {
    final bad = PaperScapeApiClient(
      baseUrl: 'http://host/api/v1',
      client: FakeClient(body: '<html>secret raw body</html>', statusCode: 500),
    );
    expect(
      () => bad.getJobStatus('job-1'),
      throwsA(predicate((e) =>
          e is ApiException && !e.toString().contains('secret raw body'))),
    );

    final timeout = PaperScapeApiClient(
      baseUrl: 'http://host/api/v1',
      client: HangingClient(),
      timeout: const Duration(milliseconds: 1),
    );
    expect(() => timeout.getJobStatus('job-1'), throwsA(isA<ApiException>()));
  });
}
