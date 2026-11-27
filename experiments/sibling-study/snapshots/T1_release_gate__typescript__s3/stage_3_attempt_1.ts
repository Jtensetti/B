import * as fs from "fs";
import * as path from "path";
import semver from "semver";

interface ArtifactInput {
  raw_path: string;
  channel: string;
  size_kb: number;
}

interface GateInput {
  min_range: string;
  artifacts: ArtifactInput[];
}

type SizeTier = "tiny" | "standard" | "large" | "oversize";

interface ParsedArtifact {
  raw: ArtifactInput;
  norm: string;
  pkg: string;
  ver: string;
  validFormat: boolean;
  sizeTier: SizeTier;
}

interface EligibilityResult {
  eligible: boolean;
  exempt: boolean;
}

interface GateOutput {
  total: number;
  eligible: number;
  oversize: number;
  total_kb: number;
  max_kb: number;
  consecutive_rejects: number;
  freeze: boolean;
  exempt: number;
}

const VALID_CHANNELS = new Set<string>(["stable", "beta", "lts"]);
const NORM_PATH_REGEX = /^[a-z0-9-]+\/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$/;

function decodePath(rawPath: string): string | null {
  try {
    return decodeURIComponent(rawPath);
  } catch {
    return null;
  }
}

function classifySizeTier(sizeKb: number): SizeTier {
  if (sizeKb < 100) {
    return "tiny";
  }
  if (sizeKb <= 1000) {
    return "standard";
  }
  if (sizeKb <= 5000) {
    return "large";
  }
  return "oversize";
}

function parseArtifact(artifact: ArtifactInput): ParsedArtifact {
  const sizeTier = classifySizeTier(artifact.size_kb);
  const decoded = decodePath(artifact.raw_path);
  if (decoded === null) {
    return {
      raw: artifact,
      norm: "",
      pkg: "",
      ver: "",
      validFormat: false,
      sizeTier,
    };
  }

  const norm = path.posix.normalize(decoded);
  const pkg = path.posix.dirname(norm);
  const ver = path.posix.basename(norm);
  const validFormat =
    NORM_PATH_REGEX.test(norm) && VALID_CHANNELS.has(artifact.channel);

  return {
    raw: artifact,
    norm,
    pkg,
    ver,
    validFormat,
    sizeTier,
  };
}

function evaluateEligibility(
  parsed: ParsedArtifact,
  minRange: string
): EligibilityResult {
  if (!parsed.validFormat || parsed.sizeTier === "oversize") {
    return { eligible: false, exempt: false };
  }
  if (semver.valid(parsed.ver) === null) {
    return { eligible: false, exempt: false };
  }
  if (semver.prerelease(parsed.ver) !== null || parsed.ver.includes("-")) {
    return { eligible: false, exempt: false };
  }

  if (semver.satisfies(parsed.ver, minRange)) {
    return { eligible: true, exempt: false };
  }

  const isLtsSecurityExempt =
    parsed.raw.channel === "lts" && parsed.pkg.includes("security");
  if (isLtsSecurityExempt) {
    return { eligible: true, exempt: true };
  }

  return { eligible: false, exempt: false };
}

function evaluateGate(input: GateInput): GateOutput {
  const total = input.artifacts.length;
  let eligible = 0;
  let oversize = 0;
  let totalKb = 0;
  let maxKb = 0;
  let consecutiveRejects = 0;
  let exempt = 0;
  let prevEligible = true;

  for (let i = 0; i < input.artifacts.length; i++) {
    const artifact = input.artifacts[i];
    const parsed = parseArtifact(artifact);

    if (parsed.sizeTier === "oversize") {
      oversize += 1;
    }

    const result = evaluateEligibility(parsed, input.min_range);
    if (result.eligible) {
      eligible += 1;
      if (result.exempt) {
        exempt += 1;
      }
    } else if (i > 0 && !prevEligible) {
      consecutiveRejects += 1;
    }
    prevEligible = result.eligible;

    totalKb += artifact.size_kb;
    if (i === 0 || artifact.size_kb > maxKb) {
      maxKb = artifact.size_kb;
    }
  }

  return {
    total,
    eligible,
    oversize,
    total_kb: totalKb,
    max_kb: maxKb,
    consecutive_rejects: consecutiveRejects,
    freeze: consecutiveRejects >= 2,
    exempt,
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const input: GateInput = JSON.parse(rawInput) as GateInput;
  const output = evaluateGate(input);
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

main();
