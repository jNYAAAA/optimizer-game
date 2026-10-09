// SensorHelper — читает датчики через LibreHardwareMonitorLib и печатает JSON.
// Сборка: csc /target:exe /out:SensorHelper.exe /reference:LibreHardwareMonitorLib.dll SensorHelper.cs
using System;
using System.Globalization;
using System.Text;
using System.Threading;
using LibreHardwareMonitor.Hardware;

internal static class SensorHelper
{
    private static string Esc(string value)
    {
        return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }

    private static void Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;

        Computer computer = new Computer();
        computer.IsCpuEnabled = true;
        computer.IsGpuEnabled = true;
        computer.IsMemoryEnabled = true;
        computer.IsMotherboardEnabled = true;
        computer.IsControllerEnabled = true;
        computer.IsStorageEnabled = true;
        computer.IsNetworkEnabled = false;

        try
        {
            computer.Open();
            Thread.Sleep(1200);

            StringBuilder builder = new StringBuilder();
            builder.Append("[");
            bool first = true;
            foreach (IHardware hardware in computer.Hardware)
            {
                Dump(hardware, builder, ref first);
            }
            builder.Append("]");
            Console.WriteLine(builder.ToString());
        }
        catch (Exception exception)
        {
            Console.WriteLine("{\"error\":\"" + Esc(exception.Message) + "\"}");
        }
        finally
        {
            try { computer.Close(); }
            catch { }
        }
    }

    private static void Dump(IHardware hardware, StringBuilder builder, ref bool first)
    {
        try { hardware.Update(); }
        catch { }

        foreach (ISensor sensor in hardware.Sensors)
        {
            if (sensor.Value == null) continue;
            if (sensor.SensorType != SensorType.Temperature && sensor.SensorType != SensorType.Fan) continue;

            if (!first) builder.Append(",");
            first = false;
            builder.Append("{\"hw\":\"").Append(Esc(hardware.Name));
            builder.Append("\",\"type\":\"").Append(sensor.SensorType.ToString());
            builder.Append("\",\"name\":\"").Append(Esc(sensor.Name));
            builder.Append("\",\"value\":");
            builder.Append(sensor.Value.Value.ToString(CultureInfo.InvariantCulture));
            builder.Append("}");
        }

        foreach (IHardware sub in hardware.SubHardware)
        {
            Dump(sub, builder, ref first);
        }
    }
}
