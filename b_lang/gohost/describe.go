// describe prints the exported functions of a Go package as JSON, using Go's own type checker.
// Usage: describe <import path or directory>
// Each function: {"name", "params": [go type], "results": [go type], "variadic": bool}.
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/build"
	"go/importer"
	"go/parser"
	"go/token"
	"go/types"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type fn struct {
	Name     string   `json:"name"`
	Params   []string `json:"params"`
	Results  []string `json:"results"`
	Variadic bool     `json:"variadic"`
}

func main() {
	target := os.Args[1]
	fset := token.NewFileSet()
	var pkg *types.Package
	var err error
	if strings.HasPrefix(target, "/") {
		bp, e := build.ImportDir(target, 0)
		if e != nil {
			fail(e)
		}
		var files []*ast.File
		for _, name := range bp.GoFiles {
			f, e := parser.ParseFile(fset, filepath.Join(target, name), nil, 0)
			if e != nil {
				fail(e)
			}
			files = append(files, f)
		}
		conf := types.Config{Importer: importer.ForCompiler(fset, "source", nil)}
		pkg, err = conf.Check(bp.Name, fset, files, nil)
	} else {
		pkg, err = importer.ForCompiler(fset, "source", nil).Import(target)
	}
	if err != nil {
		fail(err)
	}
	qualifier := func(p *types.Package) string { return p.Name() }
	var out []fn
	scope := pkg.Scope()
	names := scope.Names()
	sort.Strings(names)
	for _, name := range names {
		obj, ok := scope.Lookup(name).(*types.Func)
		if !ok || !obj.Exported() {
			continue
		}
		sig := obj.Type().(*types.Signature)
		if sig.TypeParams().Len() > 0 {
			continue
		}
		f := fn{Name: name, Variadic: sig.Variadic(), Params: []string{}, Results: []string{}}
		for i := 0; i < sig.Params().Len(); i++ {
			f.Params = append(f.Params, types.TypeString(sig.Params().At(i).Type(), qualifier))
		}
		for i := 0; i < sig.Results().Len(); i++ {
			f.Results = append(f.Results, types.TypeString(sig.Results().At(i).Type(), qualifier))
		}
		out = append(out, f)
	}
	json.NewEncoder(os.Stdout).Encode(map[string]any{"package": pkg.Name(), "functions": out})
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}
