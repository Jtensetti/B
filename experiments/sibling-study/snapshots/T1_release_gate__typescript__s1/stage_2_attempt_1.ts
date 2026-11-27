import * as fs from "fs";
import * as path from "path";
import * as semver from "semver";

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
  norm: string | null;
  pkg: string | null;
  ver: string | null;
  sizeTier: SizeTier;
  validFormat: boolean;
  eligible: boolean;
}

interface GateOutput {
  total: number;
  eligible: number;
  oversize: number;
  total_kb: number;
  max_kb: number;
  consecutive_rejects: number;
  freeze: boolean;
}

const VALID_CHANNELS: ReadonlySet<string> = new Set(["stable", "beta", "lts"]);
const NORM_PATH_PATTERN = /^[a-z0-9-]+\/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$/;

function decodeAndNormalizePath(rawPath: string): string | null {
  try {
    const decoded = decodeURIComponent(rawPath);
    return path.posix.normalize(decoded);
  } catch {
    return null;
  }
}

function isEligibleVersion(version: string, minRange: string): boolean {
  if (semver.valid(version) === null) {
    return false;
  }
  if (semver.prerelease(version) !== null) {
    return false;
  }
  return semver.satisfies(version, minRange);
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

function parseArtifact(artifact: ArtifactInput, minRange: string): ParsedArtifact {
  const sizeTier = classifySizeTier(artifact.size_kb);
  const norm = decodeAndNormalizePath(artifact.raw_path);
  if (norm === null) {
    return {
      raw: artifact,
      norm: null,
      pkg: null,
      ver: null,
      sizeTier,
      validFormat: false,
      eligible: false,
    };
  }

  const ver = path.posix.basename(norm);
  const pkg = path.posix.dirname(norm);
  const validFormat =
    NORM_PATH_PATTERN.test(norm) && VALID_CHANNELS.has(artifact.channel);
  const eligible =
    validFormat && sizeTier !== "oversize" && isEligibleVersion(ver, minRange);

  return {
    raw: artifact,
    norm,
    pkg,
    ver,
    sizeTier,
    validFormat,
    eligible,
  };
}

function evaluateGate(input: GateInput): GateOutput {
  const parsed = input.artifacts.map((artifact) =>
    parseArtifact(artifact, input.min_range)
  );

  const total = parsed.length;
  let eligible = 0;
  let oversize = 0;
  let totalKb = 0;
  let maxKb = 0;
  let consecutiveRejects = 0;

  for (let i = 0; i < parsed.length; i++) {
    const item = parsed[i];
    if (item.eligible) {
      eligible += 1;
    } else if (i > 0 && !parsed[i - 1].eligible) {
      consecutiveRejects += 1;
    }
    if (item.sizeTier === "oversize") {
      oversize += 1;
    }
    const size = item.raw.size_kb;
    totalKb += size;
    if (i === 0 || size > maxKb) {
      maxKb = size;
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
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const input: GateInput = JSON.parse(rawInput) as GateInput;
  const output = evaluateGate(input);
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

main();
