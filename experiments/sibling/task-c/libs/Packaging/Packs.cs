namespace Packaging;

/// Pack sizes and order quantities. Maintained by the warehouse team.
public static class Packs
{
    /// The smallest multiple of packSize that is at least quantity. Quantities of 0 or less give 0.
    public static int RoundUp(int quantity, int packSize)
    {
        if (packSize <= 0) throw new ArgumentException("pack size must be positive");
        if (quantity <= 0) return 0;
        return (quantity + packSize - 1) / packSize * packSize;
    }
}
