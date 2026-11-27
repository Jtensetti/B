import * as fs from "fs";
import * as path from "path";
import * as semver from "semver";

type Channel = "stable" | "beta" | "lts";
type SizeTier = "tiny" | "standard" | "large" | "oversize";

const VALID_CHANNELS: ReadonlySet<string> = new Set<Channel>([
  "stable",
  "beta",
  "lts",
]);

const ARTIFACT_PATH_PATTERN =
  /^[a-z0-9-]+\/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$/;

const KB_PER_MB = 1024;

interface ArtifactInput {
  raw_path: string;
  channel: string;
  size_kb: number;
}

interface GateInput {
  min_range: string;
  budget_mb: number;
  artifacts: ArtifactInput[];
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
  eligible_kb: number;
  within_budget: boolean;
  recommended: string | null;
}

interface EvaluatedArtifact {
  input: ArtifactInput;
  norm: string | null;
  pkg: string | null;
  ver: string | null;
  parsedVer: semver.SemVer | null;
  sizeTier: SizeTier;
  validFormat: boolean;
  eligible: boolean;
  exempt: boolean;
}

function decodeAndNormalizePath(rawPath: string): string | null {
  try {
    const decoded = decodeURIComponent(rawPath);
    return path.posix.normalize(decoded);
  } catch {
    return null;
  }
}

function isValidChannel(channel: string): channel is Channel {
  return VALID_CHANNELS.has(channel);
}

function parseNonPrereleaseSemver(ver: string): semver.SemVer | null {
  if (ver.includes("-")) {
    return null;
  }
  const parsed = semver.parse(ver);
  if (parsed === null || parsed.prerelease.length > 0) {
    return null;
  }
  return parsed;
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

function evaluateArtifact(
  artifact: ArtifactInput,
  minRange: string,
): EvaluatedArtifact {
  const sizeTier = classifySizeTier(artifact.size_kb);
  const norm = decodeAndNormalizePath(artifact.raw_path);
  if (norm === null) {
    return {
      input: artifact,
      norm: null,
      pkg: null,
      ver: null,
      parsedVer: null,
      sizeTier,
      validFormat: false,
      eligible: false,
      exempt: false,
    };
  }

  const ver = path.posix.basename(norm);
  const pkg = path.posix.dirname(norm);
  const validFormat =
    ARTIFACT_PATH_PATTERN.test(norm) && isValidChannel(artifact.channel);
  const parsedVer = validFormat ? parseNonPrereleaseSemver(ver) : null;
  const notOversize = sizeTier !== "oversize";

  const satisfiesRange =
    parsedVer !== null &&
    semver.satisfies(parsedVer, minRange, { includePrerelease: false });
  const normallyEligible = validFormat && notOversize && satisfiesRange;

  const isLtsSecurityExempt =
    validFormat &&
    artifact.channel === "lts" &&
    pkg.includes("security") &&
    parsedVer !== null &&
    notOversize;

  const eligible = normallyEligible || isLtsSecurityExempt;
  const exempt = isLtsSecurityExempt && !normallyEligible;

  return {
    input: artifact,
    norm,
    pkg,
    ver,
    parsedVer,
    sizeTier,
    validFormat,
    eligible,
    exempt,
  };
}

function evaluateGate(input: GateInput): GateOutput {
  const evaluatedArtifacts = input.artifacts.map((artifact) =>
    evaluateArtifact(artifact, input.min_range),
  );

  let eligibleCount = 0;
  let oversizeCount = 0;
  let exemptCount = 0;
  let totalKb = 0;
  let eligibleKb = 0;
  let maxKb = 0;
  let consecutiveRejects = 0;
  const eligibleVersions: string[] = [];

  for (let i = 0; i < evaluatedArtifacts.length; i++) {
    const evaluated = evaluatedArtifacts[i];

    if (evaluated.eligible) {
      eligibleCount += 1;
      eligibleKb += evaluated.input.size_kb;
      if (evaluated.parsedVer !== null) {
        eligibleVersions.push(evaluated.parsedVer.version);
      }
    } else if (i > 0 && !evaluatedArtifacts[i - 1].eligible) {
      consecutiveRejects += 1;
    }

    if (evaluated.sizeTier === "oversize") {
      oversizeCount += 1;
    }
    if (evaluated.exempt) {
      exemptCount += 1;
    }

    totalKb += evaluated.input.size_kb;
    if (i === 0 || evaluated.input.size_kb > maxKb) {
      maxKb = evaluated.input.size_kb;
    }
  }

  const budgetKb = input.budget_mb * KB_PER_MB;
  const recommended = semver.maxSatisfying(eligibleVersions, ">=0.0.0");

  return {
    total: evaluatedArtifacts.length,
    eligible: eligibleCount,
    oversize: oversizeCount,
    total_kb: totalKb,
    max_kb: maxKb,
    consecutive_rejects: consecutiveRejects,
    freeze: consecutiveRejects >= 2,
    exempt: exemptCount,
    eligible_kb: eligibleKb,
    within_budget: eligibleKb <= budgetKb,
    recommended,
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const parsedInput = JSON.parse(rawInput) as GateInput;
  const result = evaluateGate(parsedInput);
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

main();
