// Package leadtime knows how long suppliers take to deliver. Maintained by purchasing.
package leadtime

import "errors"

var days = map[string]int{
	"Nordic Timber": 12, "Baltic Steel": 9, "Lumo Lighting": 5, "Fabrikk AS": 7, "Textil Partner": 14,
}

// Suppliers lists the supplier names this package knows.
func Suppliers() []string {
	return []string{"Baltic Steel", "Fabrikk AS", "Lumo Lighting", "Nordic Timber", "Textil Partner"}
}

// Days returns the delivery time in calendar days for a supplier, or an error for an unknown supplier.
func Days(supplier string) (int, error) {
	d, ok := days[supplier]
	if !ok {
		return 0, errors.New("unknown supplier " + supplier)
	}
	return d, nil
}
