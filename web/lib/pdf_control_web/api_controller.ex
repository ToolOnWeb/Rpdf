defmodule PdfControlWeb.ApiController do
  use Phoenix.Controller, formats: [:json]
  import Plug.Conn

  @response_headers ~w(content-type content-disposition content-length x-pdf-control-message x-page-count x-page-width x-page-height x-preview-session)

  def dispatch(%{method: "GET", path_info: ["api", "health"]} = conn, _params) do
    ready = PdfControl.Engine.available?()

    json(put_status(conn, if(ready, do: 200, else: 503)), %{
      status: if(ready, do: "ok", else: "starting"),
      interface: "liveview",
      engine_ready: PdfControl.Engine.available?()
    })
  end

  def dispatch(conn, _params) do
    id = Base.encode16(:crypto.strong_rand_bytes(16), case: :lower)
    directory = Path.join(Application.fetch_env!(:pdf_control_web, :spool_root), id)
    File.mkdir_p!(directory)
    File.chmod!(directory, 0o700)

    try do
      case spool(conn, Path.join(directory, "request.body")) do
        {:ok, conn} ->
          process(conn, id, directory)

        {:error, :too_large, conn} ->
          conn
          |> put_resp_header("connection", "close")
          |> put_status(413)
          |> json(%{detail: "يتجاوز الطلب الحد المسموح."})

        _ ->
          conn
          |> put_resp_header("connection", "close")
          |> put_status(400)
          |> json(%{detail: "تعذّرت قراءة الطلب."})
      end
    catch
      :exit, _ ->
        conn
        |> put_resp_header("connection", "close")
        |> put_status(503)
        |> json(%{detail: "تعذّر الاتصال بمعالج PDF."})
    after
      # Only this request's newly created temporary files are removed.
      File.rm_rf(directory)
    end
  end

  defp process(conn, id, directory) do
    request = %{
      id: id,
      workspace: get_session(conn, :workspace_id),
      method: conn.method,
      path: conn.request_path,
      headers:
        conn.req_headers
        |> Enum.filter(fn {key, _} -> key in ["content-type", "content-length"] end)
        |> Enum.map(fn {key, value} -> [key, value] end)
    }

    case PdfControl.Engine.request(request) do
      {:ok, result} ->
        conn =
          Enum.reduce(result["headers"], conn, fn [key, value], acc ->
            if key in @response_headers, do: put_resp_header(acc, key, value), else: acc
          end)

        output = Path.join(directory, "response.body")

        if File.exists?(output),
          do: send_file(conn, result["status"], output),
          else: conn |> put_status(result["status"]) |> json(%{detail: "تعذّرت معالجة الملف."})

      {:error, :busy} ->
        conn |> put_status(503) |> json(%{detail: "المعالج مشغول، أعد المحاولة لاحقًا."})

      _ ->
        conn |> put_status(503) |> json(%{detail: "تعذّر الاتصال بمعالج PDF."})
    end
  end

  defp spool(conn, path) do
    file = File.open!(path, [:write, :binary])

    try do
      maximum =
        String.to_integer(System.get_env("PDF_CONTROL_MAX_SESSION_SIZE_MB", "512")) * 1024 * 1024 +
          2 * 1024 * 1024

      read_chunks(conn, file, 0, maximum)
    after
      File.close(file)
    end
  end

  defp read_chunks(conn, file, total, maximum) do
    case read_body(conn, length: 1_048_576, read_length: 1_048_576, read_timeout: 60_000) do
      {status, bytes, conn} when status in [:ok, :more] ->
        if total + byte_size(bytes) > maximum do
          {:error, :too_large, conn}
        else
          IO.binwrite(file, bytes)

          if status == :ok,
            do: {:ok, conn},
            else: read_chunks(conn, file, total + byte_size(bytes), maximum)
        end

      {:error, reason} ->
        {:error, reason}
    end
  end
end
