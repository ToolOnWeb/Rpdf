defmodule PdfControl.Engine do
  @moduledoc "A bounded FIFO around one persistent, isolated PDF processing process."
  use GenServer
  def start_link(options), do: GenServer.start_link(__MODULE__, options, name: __MODULE__)
  def request(request), do: GenServer.call(__MODULE__, {:request, request}, :infinity)
  def metrics, do: GenServer.call(__MODULE__, :metrics)
  def available?, do: GenServer.call(__MODULE__, :available)
  @impl true
  def init(_options) do
    Process.flag(:trap_exit, true)
    root = Application.fetch_env!(:pdf_control_web, :source_root)
    spool = Application.fetch_env!(:pdf_control_web, :spool_root)
    File.mkdir_p!(spool)
    python = Application.fetch_env!(:pdf_control_web, :python)

    port =
      Port.open(
        {:spawn_executable, String.to_charlist(python)},
        [
          :binary,
          :exit_status,
          :use_stdio,
          {:line, 65536},
          {:args, ["-u", "-m", "pdf_control.worker"]},
          {:cd, String.to_charlist(root)},
          {:env, [{~c"PDF_CONTROL_WORKER_SPOOL", String.to_charlist(spool)}]}
        ]
      )

    {:ok, %{port: port, ready: false, active: nil, queue: :queue.new(), valid_sessions: 0}}
  end

  @impl true
  def handle_call(:metrics, _from, state),
    do:
      {:reply,
       %{
         ready: state.ready,
         pending_jobs: :queue.len(state.queue) + if(state.active, do: 1, else: 0),
         valid_sessions: state.valid_sessions
       }, state}

  def handle_call(:available, _from, state), do: {:reply, state.ready, state}

  def handle_call({:request, request}, from, state) do
    limit = Application.fetch_env!(:pdf_control_web, :max_queue)

    if :queue.len(state.queue) + if(state.active, do: 1, else: 0) >= limit do
      {:reply, {:error, :busy}, state}
    else
      notify(request, :queued)
      {:noreply, dispatch(%{state | queue: :queue.in({from, request}, state.queue)})}
    end
  end

  @impl true
  def handle_info({port, {:data, {:eol, line}}}, %{port: port} = state) do
    case Jason.decode(line) do
      {:ok, %{"ready" => true, "protocol" => 1}} ->
        {:noreply, dispatch(%{state | ready: true})}

      {:ok, %{"id" => id} = result} when state.active != nil ->
        {from, request, timer} = state.active

        if id == request.id do
          Process.cancel_timer(timer)
          notify(request, if(result["status"] < 400, do: :succeeded, else: :failed))
          GenServer.reply(from, {:ok, result})

          {:noreply,
           dispatch(%{
             state
             | active: nil,
               valid_sessions: Map.get(result, "valid_sessions", state.valid_sessions)
           })}
        else
          {:stop, :protocol_mismatch, state}
        end

      _ ->
        {:stop, :invalid_worker_protocol, state}
    end
  end

  def handle_info({:job_timeout, id}, %{active: {_from, %{id: id}, _timer}} = state),
    do: {:stop, :job_timeout, state}

  def handle_info({:job_timeout, _old_id}, state), do: {:noreply, state}

  def handle_info({port, {:exit_status, status}}, %{port: port} = state),
    do: {:stop, {:worker_exit, status}, state}

  def handle_info({:EXIT, port, reason}, %{port: port} = state),
    do: {:stop, {:worker_exit, reason}, state}

  def handle_info({_port, {:data, {:noeol, _}}}, state),
    do: {:stop, :oversized_worker_protocol, state}

  @impl true
  def terminate(_reason, state) do
    if state.active do
      {from, request, timer} = state.active
      Process.cancel_timer(timer)
      notify(request, :failed)
      GenServer.reply(from, {:error, :worker_stopped})
    end

    for {from, request} <- :queue.to_list(state.queue) do
      notify(request, :failed)
      GenServer.reply(from, {:error, :worker_stopped})
    end

    case Port.info(state.port, :os_pid) do
      {:os_pid, pid} ->
        # Only the OS child created by this Engine instance is terminated.
        System.cmd("kill", ["-TERM", Integer.to_string(pid)], stderr_to_stdout: true)
        if Port.info(state.port), do: Port.close(state.port)

      nil ->
        :ok
    end

    :ok
  end

  defp dispatch(%{ready: true, active: nil} = state) do
    case :queue.out(state.queue) do
      {{:value, {from, request}}, queue} ->
        notify(request, :running)
        true = Port.command(state.port, Jason.encode!(request) <> "\n")

        timer =
          Process.send_after(
            self(),
            {:job_timeout, request.id},
            Application.fetch_env!(:pdf_control_web, :job_timeout)
          )

        %{state | queue: queue, active: {from, request, timer}}

      {:empty, _} ->
        state
    end
  end

  defp dispatch(state), do: state

  defp notify(request, status),
    do: PdfControl.Jobs.publish(request.workspace, status)
end
