// B Go host: explicit stdlib signatures, guarded JSON-lines values, --describe metadata.
package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"net/url"
	"os"
	"path"
	"regexp"
	"strings"
	"unicode/utf8"
)

type MethodDesc struct {
	Name      string            `json:"name"`
	Params    []string          `json:"params"`
	Result    string            `json:"result"`
	Semantics map[string]string `json:"semantics,omitempty"`
}

type Manifest struct {
	Schema   int                     `json:"schema"`
	Runtime  string                  `json:"runtime"`
	Packages map[string][]MethodDesc `json:"packages"`
}

func buildManifest() Manifest {
	return Manifest{
		Schema:  1,
		Runtime: "b-go-host/go1.24",
		Packages: map[string][]MethodDesc{
			"strings": {
				{Name: "Contains", Params: []string{"Text", "Text"}, Result: "Bool"},
				{Name: "Count", Params: []string{"Text", "Text"}, Result: "Int"},
				{Name: "HasPrefix", Params: []string{"Text", "Text"}, Result: "Bool"},
				{Name: "HasSuffix", Params: []string{"Text", "Text"}, Result: "Bool"},
				{Name: "Join", Params: []string{"List[Text]", "Text"}, Result: "Text"},
				{Name: "ReplaceAll", Params: []string{"Text", "Text", "Text"}, Result: "Text"},
				{Name: "Split", Params: []string{"Text", "Text"}, Result: "List[Text]"},
				{Name: "ToLower", Params: []string{"Text"}, Result: "Text"},
				{Name: "ToUpper", Params: []string{"Text"}, Result: "Text"},
				{Name: "TrimSpace", Params: []string{"Text"}, Result: "Text"},
			},
			"path": {
				{Name: "Base", Params: []string{"Text"}, Result: "Text"},
				{Name: "Clean", Params: []string{"Text"}, Result: "Text"},
				{Name: "Dir", Params: []string{"Text"}, Result: "Text"},
				{Name: "Ext", Params: []string{"Text"}, Result: "Text"},
				{Name: "Join", Params: []string{"Text", "Text"}, Result: "Text"},
				{Name: "Match", Params: []string{"Text", "Text"}, Result: "Bool"},
			},
			"net.url": {
				{Name: "PathEscape", Params: []string{"Text"}, Result: "Text"},
				{Name: "PathUnescape", Params: []string{"Text"}, Result: "Text"},
				{Name: "QueryEscape", Params: []string{"Text"}, Result: "Text"},
				{Name: "QueryUnescape", Params: []string{"Text"}, Result: "Text"},
			},
			"math": {
				{Name: "Abs", Params: []string{"Float"}, Result: "Float"},
				{Name: "Ceil", Params: []string{"Float"}, Result: "Float"},
				{Name: "Floor", Params: []string{"Float"}, Result: "Float"},
				{Name: "Hypot", Params: []string{"Float", "Float"}, Result: "Float"},
				{Name: "Mod", Params: []string{"Float", "Float"}, Result: "Float", Semantics: map[string]string{"remainder": "trunc"}},
				{Name: "Remainder", Params: []string{"Float", "Float"}, Result: "Float", Semantics: map[string]string{"remainder": "ieee"}},
				{Name: "Round", Params: []string{"Float"}, Result: "Float", Semantics: map[string]string{"rounding": "half_away_zero"}},
				{Name: "RoundToEven", Params: []string{"Float"}, Result: "Float", Semantics: map[string]string{"rounding": "half_even"}},
				{Name: "Sqrt", Params: []string{"Float"}, Result: "Float"},
			},
			"regexp": {
				{Name: "MatchString", Params: []string{"Text", "Text"}, Result: "Bool", Semantics: map[string]string{"regex_mode": "search"}},
			},
			"crypto.sha256": {
				{Name: "SumHex", Params: []string{"Text"}, Result: "Text"},
			},
			"unicode.utf8": {
				{Name: "ByteLen", Params: []string{"Text"}, Result: "Int", Semantics: map[string]string{"string_unit": "utf8_bytes"}},
				{Name: "RuneCountInString", Params: []string{"Text"}, Result: "Int", Semantics: map[string]string{"string_unit": "codepoints"}},
				{Name: "ValidString", Params: []string{"Text"}, Result: "Bool"},
			},
		},
	}
}

type Request struct {
	Package string            `json:"package"`
	Method  string            `json:"method"`
	Args    []json.RawMessage `json:"args"`
}

type Response struct {
	OK    bool   `json:"ok"`
	Value any    `json:"value,omitempty"`
	Error string `json:"error,omitempty"`
}

func argText(args []json.RawMessage, i int) (string, error) {
	if i >= len(args) {
		return "", fmt.Errorf("missing argument %d", i+1)
	}
	var s string
	if err := json.Unmarshal(args[i], &s); err != nil {
		return "", fmt.Errorf("argument %d must be Text", i+1)
	}
	return s, nil
}

func argTextList(args []json.RawMessage, i int) ([]string, error) {
	if i >= len(args) {
		return nil, fmt.Errorf("missing argument %d", i+1)
	}
	var xs []string
	if err := json.Unmarshal(args[i], &xs); err != nil {
		return nil, fmt.Errorf("argument %d must be List[Text]", i+1)
	}
	return xs, nil
}

func argFloat(args []json.RawMessage, i int) (float64, error) {
	if i >= len(args) {
		return 0, fmt.Errorf("missing argument %d", i+1)
	}
	var v float64
	if err := json.Unmarshal(args[i], &v); err != nil {
		return 0, fmt.Errorf("argument %d must be numeric", i+1)
	}
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return 0, fmt.Errorf("non-finite float rejected")
	}
	return v, nil
}

func checkFinite(v float64) (float64, error) {
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return 0, fmt.Errorf("non-finite output rejected")
	}
	return v, nil
}

func dispatch(req Request) (any, error) {
	a := req.Args
	switch req.Package {
	case "strings":
		switch req.Method {
		case "Contains":
			if len(a) != 2 {
				return nil, fmt.Errorf("expected 2 arguments")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			sub, err := argText(a, 1)
			if err != nil {
				return nil, err
			}
			return strings.Contains(s, sub), nil
		case "Count":
			if len(a) != 2 {
				return nil, fmt.Errorf("expected 2 arguments")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			sub, err := argText(a, 1)
			if err != nil {
				return nil, err
			}
			return strings.Count(s, sub), nil
		case "HasPrefix":
			if len(a) != 2 {
				return nil, fmt.Errorf("expected 2 arguments")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			p, err := argText(a, 1)
			if err != nil {
				return nil, err
			}
			return strings.HasPrefix(s, p), nil
		case "HasSuffix":
			if len(a) != 2 {
				return nil, fmt.Errorf("expected 2 arguments")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			p, err := argText(a, 1)
			if err != nil {
				return nil, err
			}
			return strings.HasSuffix(s, p), nil
		case "Join":
			if len(a) != 2 {
				return nil, fmt.Errorf("expected 2 arguments")
			}
			xs, err := argTextList(a, 0)
			if err != nil {
				return nil, err
			}
			sep, err := argText(a, 1)
			if err != nil {
				return nil, err
			}
			return strings.Join(xs, sep), nil
		case "ReplaceAll":
			if len(a) != 3 {
				return nil, fmt.Errorf("expected 3 arguments")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			oldS, err := argText(a, 1)
			if err != nil {
				return nil, err
			}
			newS, err := argText(a, 2)
			if err != nil {
				return nil, err
			}
			return strings.ReplaceAll(s, oldS, newS), nil
		case "Split":
			if len(a) != 2 {
				return nil, fmt.Errorf("expected 2 arguments")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			sep, err := argText(a, 1)
			if err != nil {
				return nil, err
			}
			return strings.Split(s, sep), nil
		case "ToLower":
			if len(a) != 1 {
				return nil, fmt.Errorf("expected 1 argument")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			return strings.ToLower(s), nil
		case "ToUpper":
			if len(a) != 1 {
				return nil, fmt.Errorf("expected 1 argument")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			return strings.ToUpper(s), nil
		case "TrimSpace":
			if len(a) != 1 {
				return nil, fmt.Errorf("expected 1 argument")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			return strings.TrimSpace(s), nil
		}
	case "path":
		switch req.Method {
		case "Base":
			if len(a) != 1 {
				return nil, fmt.Errorf("expected 1 argument")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			return path.Base(s), nil
		case "Clean":
			if len(a) != 1 {
				return nil, fmt.Errorf("expected 1 argument")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			return path.Clean(s), nil
		case "Dir":
			if len(a) != 1 {
				return nil, fmt.Errorf("expected 1 argument")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			return path.Dir(s), nil
		case "Ext":
			if len(a) != 1 {
				return nil, fmt.Errorf("expected 1 argument")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			return path.Ext(s), nil
		case "Join":
			if len(a) != 2 {
				return nil, fmt.Errorf("expected 2 arguments")
			}
			s1, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			s2, err := argText(a, 1)
			if err != nil {
				return nil, err
			}
			return path.Join(s1, s2), nil
		case "Match":
			if len(a) != 2 {
				return nil, fmt.Errorf("expected 2 arguments")
			}
			pat, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			name, err := argText(a, 1)
			if err != nil {
				return nil, err
			}
			return path.Match(pat, name)
		}
	case "net.url":
		if len(a) != 1 {
			return nil, fmt.Errorf("expected 1 argument")
		}
		s, err := argText(a, 0)
		if err != nil {
			return nil, err
		}
		switch req.Method {
		case "PathEscape":
			return url.PathEscape(s), nil
		case "PathUnescape":
			return url.PathUnescape(s)
		case "QueryEscape":
			return url.QueryEscape(s), nil
		case "QueryUnescape":
			return url.QueryUnescape(s)
		}
	case "math":
		switch req.Method {
		case "Abs", "Ceil", "Floor", "Round", "RoundToEven", "Sqrt":
			if len(a) != 1 {
				return nil, fmt.Errorf("expected 1 argument")
			}
			x, err := argFloat(a, 0)
			if err != nil {
				return nil, err
			}
			switch req.Method {
			case "Abs":
				return checkFinite(math.Abs(x))
			case "Ceil":
				return checkFinite(math.Ceil(x))
			case "Floor":
				return checkFinite(math.Floor(x))
			case "Round":
				return checkFinite(math.Round(x))
			case "RoundToEven":
				return checkFinite(math.RoundToEven(x))
			case "Sqrt":
				return checkFinite(math.Sqrt(x))
			}
		case "Hypot", "Mod", "Remainder":
			if len(a) != 2 {
				return nil, fmt.Errorf("expected 2 arguments")
			}
			x, err := argFloat(a, 0)
			if err != nil {
				return nil, err
			}
			y, err := argFloat(a, 1)
			if err != nil {
				return nil, err
			}
			switch req.Method {
			case "Hypot":
				return checkFinite(math.Hypot(x, y))
			case "Mod":
				return checkFinite(math.Mod(x, y))
			case "Remainder":
				return checkFinite(math.Remainder(x, y))
			}
		}
	case "regexp":
		if req.Method == "MatchString" {
			if len(a) != 2 {
				return nil, fmt.Errorf("expected 2 arguments")
			}
			pat, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			s, err := argText(a, 1)
			if err != nil {
				return nil, err
			}
			return regexp.MatchString(pat, s)
		}
	case "crypto.sha256":
		if req.Method == "SumHex" {
			if len(a) != 1 {
				return nil, fmt.Errorf("expected 1 argument")
			}
			s, err := argText(a, 0)
			if err != nil {
				return nil, err
			}
			sum := sha256.Sum256([]byte(s))
			return hex.EncodeToString(sum[:]), nil
		}
	case "unicode.utf8":
		if len(a) != 1 {
			return nil, fmt.Errorf("expected 1 argument")
		}
		s, err := argText(a, 0)
		if err != nil {
			return nil, err
		}
		switch req.Method {
		case "ByteLen":
			return len(s), nil
		case "RuneCountInString":
			return utf8.RuneCountInString(s), nil
		case "ValidString":
			return utf8.ValidString(s), nil
		}
	}
	return nil, fmt.Errorf("unregistered Go symbol %s.%s", req.Package, req.Method)
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--describe" {
		enc := json.NewEncoder(os.Stdout)
		_ = enc.Encode(buildManifest())
		return
	}
	if len(os.Args) != 1 {
		fmt.Fprintln(os.Stderr, "Unknown option")
		os.Exit(2)
	}
	scanner := bufio.NewScanner(os.Stdin)
	buf := make([]byte, 0, 1024*1024)
	scanner.Buffer(buf, 16*1024*1024)
	enc := json.NewEncoder(os.Stdout)
	for scanner.Scan() {
		line := scanner.Bytes()
		var req Request
		if err := json.Unmarshal(line, &req); err != nil {
			_ = enc.Encode(Response{OK: false, Error: "invalid JSON request"})
			continue
		}
		val, err := dispatch(req)
		if err != nil {
			_ = enc.Encode(Response{OK: false, Error: err.Error()})
			continue
		}
		_ = enc.Encode(Response{OK: true, Value: val})
	}
}
