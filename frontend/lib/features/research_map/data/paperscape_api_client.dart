import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../domain/selected_pdf.dart';
import 'api_exception.dart';
import 'dto/job_response.dart';
import 'dto/research_map.dart';
import 'dto/upload_response.dart';

abstract interface class PaperScapeApi {
  Future<UploadResponse> uploadPaper(SelectedPdf pdf);
  Future<JobCreateResponse> createResearchMapJob(String paperId);
  Future<JobStatusResponse> getJobStatus(String jobId);
  Future<ResearchMap> getResearchMap(String paperId);
}

typedef MultipartFactory = http.MultipartRequest Function(
    String method, Uri url);

abstract interface class MultipartSender {
  Future<http.StreamedResponse> send(http.MultipartRequest request);
}

class HttpMultipartSender implements MultipartSender {
  HttpMultipartSender(this._client);
  final http.Client _client;
  @override
  Future<http.StreamedResponse> send(http.MultipartRequest request) =>
      _client.send(request);
}

class PaperScapeApiClient implements PaperScapeApi {
  PaperScapeApiClient({
    required String baseUrl,
    http.Client? client,
    MultipartFactory? multipartFactory,
    MultipartSender? multipartSender,
    this.timeout = const Duration(seconds: 30),
    this.uploadTimeout = const Duration(minutes: 3),
  })  : _baseUri = Uri.parse(baseUrl),
        _ownsClient = client == null,
        _client = client ?? http.Client(),
        _multipartFactory =
            multipartFactory ?? ((m, u) => http.MultipartRequest(m, u)),
        _multipartSender = multipartSender;

  final bool _ownsClient;
  final Uri _baseUri;
  final http.Client _client;
  final MultipartFactory _multipartFactory;
  final MultipartSender? _multipartSender;
  final Duration timeout;
  final Duration uploadTimeout;

  Uri _uri(List<String> parts) => _baseUri.replace(pathSegments: [
        ..._baseUri.pathSegments.where((p) => p.isNotEmpty),
        ...parts,
      ]);

  void close() {
    if (_ownsClient) _client.close();
  }

  @override
  Future<UploadResponse> uploadPaper(SelectedPdf pdf) async {
    final request = _multipartFactory('POST', _uri(['papers']));
    request.files.add(http.MultipartFile.fromBytes(
      'file',
      pdf.bytes,
      filename: pdf.filename,
      contentType: MediaType('application', 'pdf'),
    ));
    try {
      final streamed = await (_multipartSender ?? HttpMultipartSender(_client))
          .send(request)
          .timeout(uploadTimeout);
      final response =
          await http.Response.fromStream(streamed).timeout(uploadTimeout);
      return _decode(response, 201, UploadResponse.fromJson);
    } on TimeoutException {
      throw const ApiException(
          code: 'timeout',
          safeMessage: 'Something went wrong. Please try again.');
    } on ApiException {
      rethrow;
    } catch (_) {
      throw const ApiException(
          code: 'network_error',
          safeMessage: 'Something went wrong. Please try again.');
    }
  }

  @override
  Future<JobCreateResponse> createResearchMapJob(String paperId) => _getOrPost(
        'POST',
        _uri(['papers', paperId, 'research-map-jobs']),
        202,
        JobCreateResponse.fromJson,
      );

  @override
  Future<JobStatusResponse> getJobStatus(String jobId) => _getOrPost(
        'GET',
        _uri(['jobs', jobId]),
        200,
        JobStatusResponse.fromJson,
      );

  @override
  Future<ResearchMap> getResearchMap(String paperId) => _getOrPost(
        'GET',
        _uri(['papers', paperId, 'research-map']),
        200,
        ResearchMap.fromJson,
      );

  Future<T> _getOrPost<T>(String method, Uri uri, int ok,
      T Function(Map<String, Object?>) fromJson) async {
    try {
      final response = method == 'GET'
          ? await _client.get(uri).timeout(timeout)
          : await _client.post(uri).timeout(timeout);
      return _decode(response, ok, fromJson);
    } on TimeoutException {
      throw const ApiException(
          code: 'timeout',
          safeMessage: 'Something went wrong. Please try again.');
    } on ApiException {
      rethrow;
    } catch (_) {
      throw const ApiException(
          code: 'network_error',
          safeMessage: 'Something went wrong. Please try again.');
    }
  }

  T _decode<T>(http.Response response, int ok,
      T Function(Map<String, Object?>) fromJson) {
    if (response.statusCode != ok) {
      throw parseApiError(response.statusCode, response.body);
    }
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, Object?>) throw const ParseException();
      return fromJson(decoded);
    } on ApiException {
      rethrow;
    } catch (_) {
      throw const ParseException();
    }
  }
}
