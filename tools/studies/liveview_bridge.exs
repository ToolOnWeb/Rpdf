# Same PDF engine invoked by Elixir: persistent process vs a fresh Python process/job.
[folder] = System.argv()
python = Path.expand(".venv/bin/python")
script = Path.expand("tools/studies/liveview_baseline.py")
measure = fn mode, fun ->
  fun.()
  samples = for _ <- 1..7 do
    {us, :ok} = :timer.tc(fun)
    us / 1000
  end
  sorted = Enum.sort(samples)
  IO.puts(Enum.join([mode, Enum.at(sorted, 3), hd(sorted), List.last(sorted)] ++ samples, "\t"))
end
measure.("fresh_python_per_job", fn ->
  {output, 0} = System.cmd(python, [script, "--worker", folder])
  true = String.trim(output) == "ok"
  :ok
end)
port = Port.open({:spawn_executable, python}, [:binary, :exit_status, {:args, ["-u", script, "--persistent", folder]}, {:line, 4096}])
receive do
  {^port, {:data, {:eol, "ready"}}} -> :ok
after 10000 -> raise "worker startup timeout"
end
measure.("persistent_python_port", fn ->
  true = Port.command(port, "merge40\n")
  receive do
    {^port, {:data, {:eol, "ok"}}} -> :ok
    {^port, {:exit_status, status}} -> raise "worker exited #{status}"
  after 10000 -> raise "worker response timeout"
  end
end)
Port.command(port, "quit\n")
receive do
  {^port, {:exit_status, 0}} -> :ok
after 10000 -> raise "worker shutdown timeout"
end
