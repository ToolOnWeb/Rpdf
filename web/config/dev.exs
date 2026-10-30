import Config

config :pdf_control_web, PdfControlWeb.Endpoint,
  server: false,
  http: [ip: {127, 0, 0, 1}, port: 4000],
  check_origin: false
