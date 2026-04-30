"""``forgelm deploy`` dispatcher."""

from __future__ import annotations

import json
import sys

from .._exit_codes import EXIT_TRAINING_ERROR
from .._logging import logger


def _run_deploy_cmd(args, output_format: str) -> None:
    """Dispatch the ``forgelm deploy`` subcommand."""
    from ...deploy import HFEndpointsOptions, generate_deploy_config

    result = generate_deploy_config(
        model_path=args.model_path,
        target=args.target,
        output_path=args.output,
        system_prompt=args.system,
        max_length=args.max_length,
        trust_remote_code=args.trust_remote_code,
        gpu_memory_utilization=args.gpu_memory_utilization,
        port=args.port,
        hf_endpoints=HFEndpointsOptions(vendor=getattr(args, "vendor", "aws")),
    )

    if output_format == "json":
        print(
            json.dumps(
                {
                    "success": result.success,
                    "target": result.target,
                    "output_path": result.output_path,
                    "error": result.error,
                },
                indent=2,
            )
        )
    else:
        if result.success:
            logger.info("Deploy config written: %s (target=%s)", result.output_path, result.target)
        else:
            logger.error("Deploy config generation failed: %s", result.error)

    if not result.success:
        sys.exit(EXIT_TRAINING_ERROR)
