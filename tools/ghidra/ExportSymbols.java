/* Export every non-default-named function and label to a plain-text TSV.
 *
 * The Ghidra database embeds the executable and is therefore disc content: it lives in
 * work/ and is disposable. This TSV is the durable artifact — addresses and names are
 * facts we found, not the game's bytes. ImportSymbols.java is the inverse, so a fresh
 * analysis can be re-labelled from the tracked file.
 *
 * Deliberately NOT exported: bytes, the contents of strings, decompilation, comments.
 * A comment can quote the Japanese script; a name cannot. Keep it that way.
 *
 * research/tooling-setup.md owns the invocation and the verification receipts.
 *
 * @category Boku
 */

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.framework.options.Options;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Program;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolType;
import ghidra.program.model.symbol.SourceType;

public class ExportSymbols extends GhidraScript {

	private static final String[] COLUMNS = { "address", "kind", "name", "size", "source", "namespace" };

	/* Mirrors PsxLoader.PSYQ_VER_OPTION. Not referenced directly: ghidra_psx_ldr is an
	 * optional extension, and a hard reference would make this script fail to compile
	 * wherever the loader is not installed. */
	private static final String PSYQ_VER_OPTION = "PsyQ Version";

	private static final class Row {
		long addr;
		String kind, name, source, namespace;
		long size;
	}

	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length != 1) {
			throw new IllegalArgumentException(
				"usage: ExportSymbols.java <output.tsv> (got " + args.length + " args)");
		}
		File out = new File(args[0]);
		File parent = out.getAbsoluteFile().getParentFile();
		if (parent != null) {
			parent.mkdirs();
		}

		List<Row> rows = new ArrayList<>();
		// getAllSymbols(false) omits Ghidra's dynamic placeholders (FUN_/LAB_/DAT_);
		// the SourceType check then drops anything else still carrying DEFAULT.
		for (Symbol sym : currentProgram.getSymbolTable().getAllSymbols(false)) {
			monitor.checkCancelled();
			if (sym.isExternal() || sym.isDynamic() || sym.getSource() == SourceType.DEFAULT) {
				continue;
			}
			SymbolType type = sym.getSymbolType();
			if (type != SymbolType.FUNCTION && type != SymbolType.LABEL) {
				continue;
			}
			Row r = new Row();
			r.addr = sym.getAddress().getOffset();
			r.kind = (type == SymbolType.FUNCTION) ? "FUNC" : "LABEL";
			r.name = sym.getName();
			r.source = sym.getSource().name();
			r.namespace = sym.getParentNamespace().getName(true);
			r.size = sizeOf(sym, type);
			rows.add(r);
		}

		// All four keys, so the order never falls through to the symbol table's own
		// iteration order, which is not stable across databases. caseD_0 already appears
		// in twenty-odd switchD_* namespaces, so address+kind+name is one shared case
		// target away from being ambiguous.
		rows.sort(Comparator.<Row> comparingLong(r -> r.addr)
				.thenComparing(r -> r.kind)
				.thenComparing(r -> r.name)
				.thenComparing(r -> r.namespace));

		try (BufferedWriter w = new BufferedWriter(
			new OutputStreamWriter(new FileOutputStream(out), StandardCharsets.UTF_8))) {
			writeHeader(w, rows.size());
			for (Row r : rows) {
				// Locale.ROOT, not the default: Formatter localizes %d (not %x), so on a JVM
				// whose locale uses non-Latin digits every size field would emit non-ASCII and
				// the tracked file would diff wholesale.
				w.write(String.format(Locale.ROOT, "%08x\t%s\t%s\t%d\t%s\t%s\n",
					r.addr, r.kind, r.name, r.size, r.source, r.namespace));
			}
		}
		println("ExportSymbols: wrote " + rows.size() + " symbols to " + out.getAbsolutePath());
	}

	private long sizeOf(Symbol sym, SymbolType type) {
		if (type == SymbolType.FUNCTION) {
			Function f = getFunctionAt(sym.getAddress());
			return (f == null) ? 0 : f.getBody().getNumAddresses();
		}
		Data d = getDataAt(sym.getAddress());
		return (d == null || !d.isDefined()) ? 0 : d.getLength();
	}

	/* Provenance, not content: which dump these addresses belong to, and what the PSX
	 * loader decided about it. A stranger with a different dump needs to know the names
	 * were derived from a binary whose hash is not theirs. */
	private void writeHeader(BufferedWriter w, int count) throws Exception {
		w.write("# Symbols exported from Ghidra by tools/ghidra/ExportSymbols.java\n");
		w.write("# program\t" + currentProgram.getName() + "\n");
		w.write("# sha256\t" + nullSafe(currentProgram.getExecutableSHA256()) + "\n");
		w.write("# language\t" + currentProgram.getLanguageID() + "\n");
		w.write("# image-base\t" + currentProgram.getImageBase() + "\n");
		String psyq = findPsyqVersion();
		if (psyq != null) {
			w.write("# psyq-version\t" + psyq + "\n");
		}
		w.write("# symbols\t" + count + "\n");
		w.write("#" + String.join("\t", COLUMNS) + "\n");
	}

	private String nullSafe(String s) {
		return (s == null) ? "" : s;
	}

	/* The PSX loader records the PsyQ release it detected as a Program Information
	 * property named by PsxLoader.PSYQ_VER_OPTION. Do NOT widen this to any option whose
	 * name mentions PsyQ: the Analyzers category also carries "PsyQ Signatures" (a
	 * boolean) and "PsyQ Version if not found" (the fallback, not the detection), and a
	 * substring match reports one of those instead — a header line that reads like a
	 * measurement and is not one. */
	private String findPsyqVersion() {
		Options info = currentProgram.getOptions(Program.PROGRAM_INFO);
		for (String name : info.getOptionNames()) {
			if (name.equals(PSYQ_VER_OPTION)) {
				return info.getValueAsString(name);
			}
		}
		return null;
	}
}
