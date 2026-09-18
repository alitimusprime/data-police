window.addEventListener('load', function () {
  window.ui = SwaggerUIBundle({
    url: '/api/openapi.json',
    dom_id: '#swagger-ui',
    deepLinking: true,
    requestInterceptor: function (request) {
      request.headers['X-DP-Request'] = '1';
      return request;
    },
  });
});
