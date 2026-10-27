#include "Arduino.h"
#include "esp_camera.h"
#include "esp_http_server.h"
#include <stdio.h>
#include <string.h>

static httpd_handle_t capture_httpd = NULL;
static httpd_handle_t stream_httpd = NULL;

// GET /capture on port 80 returns one JPEG image.
static esp_err_t custom_capture_handler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb == NULL) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }

  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  esp_err_t result = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return result;
}

// GET /stream on port 81 returns a live MJPEG stream.
static esp_err_t custom_stream_handler(httpd_req_t *req) {
  esp_err_t result = ESP_OK;
  char part_buf[64];
  const char *content_type = "multipart/x-mixed-replace;boundary=frame";
  const char *boundary = "\r\n--frame\r\n";
  const char *part = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

  result = httpd_resp_set_type(req, content_type);
  if (result != ESP_OK) return result;

  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");

  while (true) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb == NULL) {
      result = ESP_FAIL;
      break;
    }

    if (fb->format != PIXFORMAT_JPEG) {
      esp_camera_fb_return(fb);
      result = ESP_FAIL;
      break;
    }

    result = httpd_resp_send_chunk(req, boundary, strlen(boundary));
    if (result == ESP_OK) {
      int hlen = snprintf(part_buf, sizeof(part_buf), part, (unsigned int)fb->len);
      if (hlen < 0 || hlen >= (int)sizeof(part_buf)) {
        result = ESP_FAIL;
      } else {
        result = httpd_resp_send_chunk(req, part_buf, hlen);
      }
    }
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    }

    esp_camera_fb_return(fb);
    if (result != ESP_OK) break;
    delay(30);
  }
  return result;
}

void startCameraServer() {
  httpd_uri_t capture_uri = {};
  capture_uri.uri = "/capture";
  capture_uri.method = HTTP_GET;
  capture_uri.handler = custom_capture_handler;
  capture_uri.user_ctx = NULL;

  httpd_uri_t stream_uri = {};
  stream_uri.uri = "/stream";
  stream_uri.method = HTTP_GET;
  stream_uri.handler = custom_stream_handler;
  stream_uri.user_ctx = NULL;

  httpd_config_t capture_config = HTTPD_DEFAULT_CONFIG();
  capture_config.server_port = 80;
  capture_config.ctrl_port = 32768;
  esp_err_t capture_result = httpd_start(&capture_httpd, &capture_config);

  if (capture_result == ESP_OK) {
    esp_err_t reg_result = httpd_register_uri_handler(capture_httpd, &capture_uri);
    Serial.println(reg_result == ESP_OK
      ? "Capture server ready on port 80."
      : "Capture URI registration failed.");
  } else {
    Serial.printf("Capture server start failed: %d\n", (int)capture_result);
  }

  httpd_config_t stream_config = HTTPD_DEFAULT_CONFIG();
  stream_config.server_port = 81;
  stream_config.ctrl_port = 32769;
  esp_err_t stream_result = httpd_start(&stream_httpd, &stream_config);

  if (stream_result == ESP_OK) {
    esp_err_t reg_result = httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.println(reg_result == ESP_OK
      ? "Live stream server ready on port 81."
      : "Stream URI registration failed.");
  } else {
    Serial.printf("Stream server start failed: %d\n", (int)stream_result);
  }
}