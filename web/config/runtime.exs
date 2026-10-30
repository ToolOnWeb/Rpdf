import Config
root = System.get_env("PDF_CONTROL_ROOT", Path.expand("../..", __DIR__))

config :pdf_control_web,
  source_root: root,
  python: System.get_env("PDF_CONTROL_PYTHON", Path.join(root, ".venv/bin/python")),
  spool_root:
    System.get_env("PDF_CONTROL_SPOOL", Path.join(System.tmp_dir!(), "pdf-control-liveview")),
  max_queue: String.to_integer(System.get_env("PDF_CONTROL_MAX_QUEUE", "8")),
  job_timeout: String.to_integer(System.get_env("PDF_CONTROL_JOB_TIMEOUT_MS", "300000"))

if System.get_env("PHX_SERVER") in ["true", "1"] do
  config :pdf_control_web, PdfControlWeb.Endpoint,
    server: true,
    http: [ip: {127, 0, 0, 1}, port: String.to_integer(System.get_env("PORT", "4000"))]
end

if config_env() == :prod do
  secret = System.fetch_env!("SECRET_KEY_BASE")
  if byte_size(secret) < 64, do: raise("SECRET_KEY_BASE must contain at least 64 bytes")
  host = System.fetch_env!("PHX_HOST")
  config :pdf_control_web, :public_origin, "https://" <> host

  config :pdf_control_web, PdfControlWeb.Endpoint,
    secret_key_base: secret,
    url: [host: host, scheme: "https", port: 443],
    check_origin: ["https://" <> host]
end
