defmodule PdfControl.Metrics do
  @moduledoc "Loopback release observability. No document names, bytes or tokens."
  use GenServer
  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  def request(delta), do: GenServer.cast(__MODULE__, {:request, delta})
  def track(pid), do: GenServer.call(__MODULE__, {:track, pid})
  def counters, do: GenServer.call(__MODULE__, :counters)
  @impl true
  def init(_), do: {:ok, %{requests: 0, views: %{}}}
  @impl true
  def handle_call(:counters, _, state),
    do: {:reply, %{active_requests: state.requests + map_size(state.views)}, state}

  def handle_call({:track, pid}, _, state) do
    views =
      if Map.has_key?(state.views, pid),
        do: state.views,
        else: Map.put(state.views, pid, Process.monitor(pid))

    {:reply, :ok, %{state | views: views}}
  end

  @impl true
  def handle_cast({:request, delta}, state),
    do: {:noreply, %{state | requests: max(0, state.requests + delta)}}

  @impl true
  def handle_info({:DOWN, _ref, :process, pid, _reason}, state),
    do: {:noreply, %{state | views: Map.delete(state.views, pid)}}
end

defmodule PdfControlWeb.Release do
  import Plug.Conn
  def init(opts), do: opts

  def call(conn, _) do
    release = System.get_env("PM_RELEASE_ID")

    if conn.request_path == "/__pm_release_health" do
      if release && Regex.match?(~r/^release-[a-f0-9]{32}$/, release) &&
           conn.remote_ip in [{127, 0, 0, 1}, {0, 0, 0, 0, 0, 0, 0, 1}] do
        engine = PdfControl.Engine.metrics()
        data = PdfControl.Metrics.counters() |> Map.merge(engine) |> Map.put(:release, release)

        conn
        |> put_resp_content_type("application/json")
        |> put_resp_header("cache-control", "no-store")
        |> send_resp(if(engine.ready, do: 200, else: 503), Jason.encode!(data))
      else
        send_resp(conn, 404, "")
      end
    else
      conn =
        if release && Regex.match?(~r/^release-[a-f0-9]{32}$/, release),
          do: put_resp_header(conn, "x-pm-release", release),
          else: conn

      PdfControl.Metrics.request(1)

      try do
        PdfControlWeb.Router.call(conn, [])
      after
        PdfControl.Metrics.request(-1)
      end
    end
  end
end
