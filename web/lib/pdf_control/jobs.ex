defmodule PdfControl.Jobs do
  @moduledoc "Bounded recent task state, independent of browser connections and worker restarts."
  use GenServer
  def start_link(options), do: GenServer.start_link(__MODULE__, options, name: __MODULE__)
  def status(workspace), do: GenServer.call(__MODULE__, {:status, workspace})
  def publish(workspace, status), do: GenServer.cast(__MODULE__, {:publish, workspace, status})
  @impl true
  def init(_) do
    :timer.send_interval(60_000, :expire)
    {:ok, %{}}
  end

  @impl true
  def handle_call({:status, workspace}, _from, state) do
    {:reply,
     case Map.get(state, workspace) do
       {status, _} -> status
       nil -> nil
     end, state}
  end

  @impl true
  def handle_cast({:publish, workspace, status}, state) do
    Phoenix.PubSub.broadcast(PdfControl.PubSub, "workspace:" <> workspace, {:job, status})
    # Store no filenames, file bytes, credentials or document data.
    state = Map.put(state, workspace, {status, System.monotonic_time(:second)})
    maximum = Application.get_env(:pdf_control_web, :max_statuses, 1024)

    state =
      if map_size(state) > maximum do
        {oldest, _} = Enum.min_by(state, fn {_, {_, time}} -> time end)
        Map.delete(state, oldest)
      else
        state
      end

    {:noreply, state}
  end

  @impl true
  def handle_info(:expire, state) do
    cutoff = System.monotonic_time(:second) - 3600
    {:noreply, Map.filter(state, fn {_, {_, time}} -> time >= cutoff end)}
  end
end
