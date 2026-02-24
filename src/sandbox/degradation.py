import sys
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from src.utils.cpp_execution import run_program, ExecutionLimits

class DegradationVerdict(Enum):
    RESOLVED_WA = "RESOLVED_WA"    # Stage 2/3 confirmation: Candidate code is definitively WA
    RESOLVED_AC = "RESOLVED_AC"    # Stage 2/3 confirmation: Candidate code is definitively AC
    REJECTED = "REJECTED"          # Stage 4 fallback: Hacker payload was useless, discard
    AC = "AC"                      # Stage 1 original match: Output exactly matches Oracle
    WA = "WA"                      # Stage 1 mismatch: Output differs from Oracle
    SYSTEM_ERROR = "SYSTEM_ERROR"  # Failsafe for sandbox/disk crashes

class DegradationPipeline:
    """
    4-Stage Verification Degradation Pipeline for handling Oracle TLE.
    Ref: genesis/v1/04_SYSTEM_DESIGN/sandbox-system.md
    """
    def __init__(self, llm_client=None):
        self.llm = llm_client
        
    def evaluate(
        self,
        oracle_exe: Path,
        candidate_exe: Path,
        input_text: str,
        limits: Optional[ExecutionLimits] = None,
        problem_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[DegradationVerdict, str, str]:
        """
        Runs the full 4-stage pipeline given a generated input.
        Returns: (Verdict, CandidateOutput, OracleOutput/ErrorMessage)
        """
        if limits is None:
            limits = ExecutionLimits.default_run()
            
        # Run Candidate code first
        cand_ret, cand_out, cand_err = run_program(candidate_exe, input_text=input_text, limits=limits)
        
        # 124 format mapped from cpp_execution.py for timeouts
        if cand_ret == 124:
            return DegradationVerdict.WA, "TLE_CANDIDATE", "Candidate Code exceeded time limit."
        elif cand_ret != 0:
            return DegradationVerdict.WA, "RE_CANDIDATE", f"Candidate Runtime Error: {cand_err}"
            
        cand_out = cand_out.strip()
        
        # STAGE 1: Standard Brute-Force Oracle execution with expanded leeway
        oracle_limits = ExecutionLimits(
            cpu_seconds=limits.cpu_seconds * 5 if limits.cpu_seconds else None,
            wall_seconds=limits.wall_seconds * 5 if limits.wall_seconds else None,
            memory_bytes=limits.memory_bytes,
            fsize_bytes=limits.fsize_bytes,
            nproc=limits.nproc,
            nofile=limits.nofile
        )
        
        or_ret, or_out, or_err = run_program(oracle_exe, input_text=input_text, limits=oracle_limits)
        
        # If the Oracle succeeds normally, string-compare the result
        if or_ret == 0:
            or_out = or_out.strip()
            if cand_out == or_out:
                return DegradationVerdict.AC, cand_out, or_out
            else:
                return DegradationVerdict.WA, cand_out, or_out
                
        # If the Oracle crashed but it wasn't a TLE (e.g., RE/MLE), the Oracle itself is broken
        if or_ret != 124:
            return DegradationVerdict.REJECTED, cand_out, f"Oracle Error (Not TLE): {or_err}"
            
        # Oracle TLE confirmed. Proceed to Degradation Steps.
        
        # STAGE 2: Property Validator (e.g., N-Queens invariant, Graph reachability)
        property_validated = self._stage_2_property_validation(input_text, cand_out, problem_metadata)
        if property_validated is not None:
            verdict = DegradationVerdict.RESOLVED_AC if property_validated else DegradationVerdict.RESOLVED_WA
            return verdict, cand_out, "[Stage 2] Property Validated via Metadata"
            
        # STAGE 3: Hybrid LLM Consensus
        consensus = self._stage_3_llm_consensus(input_text, cand_out, problem_metadata)
        if consensus is not None:
            verdict = DegradationVerdict.RESOLVED_AC if consensus else DegradationVerdict.RESOLVED_WA
            return verdict, cand_out, "[Stage 3] LLM Consensus Reached"
            
        # STAGE 4: State Rejection (Throw out the hacker payload)
        return DegradationVerdict.REJECTED, cand_out, "[Stage 4] Oracle TLE; Validator & Consensus Failed."
        
    def _stage_2_property_validation(
        self, input_text: str, candidate_output: str, metadata: Optional[Dict[str, Any]]
    ) -> Optional[bool]:
        # To be implemented using problem metadata constraints
        return None
        
    def _stage_3_llm_consensus(
        self, input_text: str, candidate_output: str, metadata: Optional[Dict[str, Any]]
    ) -> Optional[bool]:
        # To be implemented using self.llm
        return None
