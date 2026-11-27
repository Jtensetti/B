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

interface GateOutput {
  total: number;
  eligible: number;
  oversize: number;
  total_kb: number;
  max_kb: number;
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

function isEligible(parsed: ParsedArtifact, minRange: string): boolean {
  if (!parsed.validFormat || parsed.sizeTier === "oversize") {
    return false;
  }
  if (semver.valid(parsed.ver) === null) {
    return false;
  }
  if (semver.prerelease(parsed.ver) !== null) {
    return false;
  }
  return semver.satisfies(parsed.ver, minRange);
}

function evaluateGate(input: GateInput): GateOutput {
  const total = input.artifacts.length;
  let eligible = 0;
  let oversize = 0;
  let totalKb = 0;
  let maxKb = 0;

  for (let i = 0; i < input.artifacts.length; i++) {
    const artifact = input.artifacts[i];
    const parsed = parseArtifact(artifact);

    if (parsed.sizeTier === "oversize") {
      oversize += 1;
    }

    if (isEligible(parsed, input.min_range)) {
      eligible += 1;
    }

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
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const input: GateInput = JSON.parse(rawInput) as GateInput;
  const output = evaluateGate(input);
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

main();
