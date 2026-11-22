#:property PublishAot=false
// The probe uses small Int32 operands with nonzero divisors.
using System;
using System.Globalization;

string? line;
while ((line = Console.ReadLine()) != null)
{
    string[] parts = line.Split(' ');
    int a = int.Parse(parts[0], CultureInfo.InvariantCulture);
    int b = int.Parse(parts[1], CultureInfo.InvariantCulture);
    int sign = a < 0 ? -1 : (a > 0 ? 1 : 0);
    Console.WriteLine($"{a % b} {sign}");
}
