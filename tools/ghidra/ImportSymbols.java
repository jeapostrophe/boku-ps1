/* Apply a tracked symbol TSV to a program — the inverse of ExportSymbols.java.
 *
 * Run this against a program that has ALREADY been auto-analysed. It renames what
 * analysis found and adds what analysis missed; it does not reconstruct a program from
 * the TSV. On a `-noanalysis` import there is no disassembly, so Ghidra cannot derive a
 * function body and every FUNC row fails — which is why this script insists on finding
 * or making a function per FUNC row and refuses to claim success otherwise.
 *
 * The `size` column is NOT applied. It is a fact about the program for a human reading
 * the file, and Ghidra derives the real body from the code. So a re-export reproduces
 * the sizes because the analyzer regenerates them, not because this script restored
 * them; do not read the round-trip as proof that sizes travel in the TSV.
 *
 * research/tooling-setup.md owns the invocation and the verification receipts.
 *
 * @category Boku
 */

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Namespace;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.SymbolTable;
import ghidra.util.exception.DuplicateNameException;
import ghidra.util.exception.InvalidInputException;

public class ImportSymbols extends GhidraScript {

	/* Must match ExportSymbols.COLUMNS. Checked rather than assumed: if a column is ever
	 * inserted or reordered, the field indices below silently misread — swapping kind and
	 * name would apply 2561 valid-looking wrong symbols. */
	private static final String COLUMN_HEADER = "#address\tkind\tname\tsize\tsource\tnamespace";

	@Override
	public void run() throws Exception {
		String[] args = getScriptArgs();
		if (args.length != 1) {
			throw new IllegalArgumentException(
				"usage: ImportSymbols.java <input.tsv> (got " + args.length + " args)");
		}
		File in = new File(args[0]);
		if (!in.isFile()) {
			throw new IllegalArgumentException("no such file: " + in.getAbsolutePath());
		}

		SymbolTable symtab = currentProgram.getSymbolTable();
		int applied = 0, created = 0, skipped = 0, lineNo = 0;
		String tsvSha = null;
		boolean sawColumnHeader = false;

		try (BufferedReader r = new BufferedReader(
			new InputStreamReader(new FileInputStream(in), StandardCharsets.UTF_8))) {
			String line;
			while ((line = r.readLine()) != null) {
				monitor.checkCancelled();
				lineNo++;
				if (line.isEmpty()) {
					continue;
				}
				if (line.charAt(0) == '#') {
					if (line.startsWith("# sha256\t")) {
						tsvSha = line.substring("# sha256\t".length()).trim();
					}
					else if (line.startsWith("#address")) {
						if (!line.equals(COLUMN_HEADER)) {
							throw new IllegalArgumentException("line " + lineNo +
								": column header is\n  " + line + "\nbut this script reads\n  " +
								COLUMN_HEADER);
						}
						sawColumnHeader = true;
						// Everything the header can tell us is now known; check it before
						// writing anything, so a mismatched TSV touches nothing.
						checkProvenance(tsvSha);
					}
					continue;
				}
				if (!sawColumnHeader) {
					throw new IllegalArgumentException("line " + lineNo +
						": data before the '" + COLUMN_HEADER + "' line; this is not an" +
						" ExportSymbols.java file");
				}

				String[] f = line.split("\t", -1);
				if (f.length != 6) {
					throw new IllegalArgumentException(
						"line " + lineNo + ": expected 6 tab-separated fields, got " + f.length);
				}
				String kind = f[1];
				String name = f[2];
				// f[3] is size — informational, see the header comment.
				SourceType source = SourceType.valueOf(f[4]);
				Address addr = currentProgram.getAddressFactory()
						.getDefaultAddressSpace()
						.getAddress(Long.parseUnsignedLong(f[0], 16));

				if (!currentProgram.getMemory().contains(addr)) {
					printerr("line " + lineNo + ": " + addr + " (" + name +
						") is not in this program's memory");
					skipped++;
					continue;
				}

				Namespace ns = resolveNamespace(f[5]);

				if ("FUNC".equals(kind)) {
					Function fn = getFunctionAt(addr);
					if (fn == null) {
						fn = createFunction(addr, name);
						if (fn == null) {
							printerr("line " + lineNo + ": no function at " + addr +
								" and Ghidra could not derive one — is this program analysed?");
							skipped++;
							continue;
						}
						created++;
					}
					fn.setName(name, source);
					fn.setParentNamespace(ns);
					applied++;
				}
				else if ("LABEL".equals(kind)) {
					symtab.createLabel(addr, name, ns, source);
					applied++;
				}
				else {
					throw new IllegalArgumentException(
						"line " + lineNo + ": unknown kind '" + kind + "'");
				}
			}
		}

		if (!sawColumnHeader) {
			throw new IllegalArgumentException(
				"no '" + COLUMN_HEADER + "' line; this is not an ExportSymbols.java file");
		}
		println("ImportSymbols: applied " + applied + " symbols (" + created +
			" new functions, " + skipped + " skipped) from " + in.getAbsolutePath());
		if (skipped > 0) {
			throw new IllegalStateException(skipped +
				" rows did not apply; see the errors above. Refusing to report success.");
		}
	}

	/* The guard that makes the `# sha256` header more than decoration.
	 *
	 * Without it, applying this TSV to a different regional build of the same game would
	 * succeed silently: every address still lands inside the loaded image, so the
	 * out-of-memory check below never fires, and 2561 wrong names get applied over a
	 * clean analysis. The hash is the only field that can tell the two apart. */
	private void checkProvenance(String tsvSha) {
		String progSha = currentProgram.getExecutableSHA256();
		if (tsvSha == null || tsvSha.isEmpty()) {
			printerr("ImportSymbols: the TSV carries no '# sha256' line; cannot confirm it " +
				"describes this program.");
			return;
		}
		if (progSha == null || progSha.isEmpty()) {
			printerr("ImportSymbols: this program records no SHA-256; cannot confirm the TSV " +
				"describes it.");
			return;
		}
		if (!tsvSha.equalsIgnoreCase(progSha)) {
			throw new IllegalStateException("this TSV was exported from a different binary.\n" +
				"  TSV     sha256 " + tsvSha + "\n" +
				"  program sha256 " + progSha + "\n" +
				"Applying it would put 'correct' names on the wrong addresses.");
		}
		println("ImportSymbols: sha256 matches this program (" + progSha + ")");
	}

	/* ExportSymbols writes Namespace.getName(true), so "Global" for the global namespace
	 * and "a::b" for anything nested. Rebuild the chain, creating what is missing. */
	private Namespace resolveNamespace(String path)
			throws InvalidInputException, DuplicateNameException {
		Namespace global = currentProgram.getGlobalNamespace();
		if (path == null || path.isEmpty() || path.equals(global.getName())) {
			return global;
		}
		Namespace ns = global;
		for (String part : path.split("::")) {
			if (part.equals(global.getName()) && ns == global) {
				continue;
			}
			Namespace child = currentProgram.getSymbolTable().getNamespace(part, ns);
			if (child == null) {
				child = currentProgram.getSymbolTable()
						.createNameSpace(ns, part, SourceType.IMPORTED);
			}
			ns = child;
		}
		return ns;
	}
}
