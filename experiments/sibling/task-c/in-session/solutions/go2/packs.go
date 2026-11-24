package main

// Port of libs/Packaging (C#): Packs.RoundUp.

import "errors"

// roundUp is the smallest multiple of packSize that is at least quantity; 0 for quantities of 0 or less.
func roundUp(quantity, packSize int) (int, error) {
	if packSize <= 0 {
		return 0, errors.New("pack size must be positive")
	}
	if quantity <= 0 {
		return 0, nil
	}
	return (quantity + packSize - 1) / packSize * packSize, nil
}
