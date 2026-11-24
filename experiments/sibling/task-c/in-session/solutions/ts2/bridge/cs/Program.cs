using Packaging;

// Reads "quantity pack" per line and prints Packs.RoundUp(quantity, pack) for each.
string? line;
while ((line = Console.ReadLine()) is not null)
{
    var parts = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
    Console.WriteLine(Packs.RoundUp(int.Parse(parts[0]), int.Parse(parts[1])));
}
