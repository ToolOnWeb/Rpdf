import Config

config :pdf_control_web, PdfControlWeb.Endpoint,
  server: false,
  http: [ip: {127, 0, 0, 1}, port: 4002]

config :logger, level: :warning
