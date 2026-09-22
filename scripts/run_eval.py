#!/usr/bin/env python3
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import uuid

from app.config import settings
from app.ai.base import get_provider
from app.email.parser import NormalizedEmail
from app.services.triage import analyze_email

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_eval():
    eval_file = Path("tests/eval/dataset.jsonl")
    if not eval_file.exists():
        logger.error("Dataset not found at %s", eval_file)
        return
        
    provider = get_provider()
    
    total = 0
    correct_category = 0
    correct_notification = 0
    
    results = []

    with eval_file.open() as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            
            email = NormalizedEmail(
                message_id=str(uuid.uuid4()),
                thread_id="thread",
                sender=data["sender"],
                recipients=["me@example.com"],
                cc=[],
                subject=data["subject"],
                body_text=data["body_text"],
                snippet=data["body_text"][:50],
                received_at=datetime.now(timezone.utc),
                labels=[],
                has_attachments=False
            )
            
            logger.info("Evaluating: %s", data["subject"])
            try:
                analysis = analyze_email(provider, email)
                
                predicted_should_notify = analysis.importance_score >= 7
                gold_should_notify = data["gold_should_notify"]
                
                cat_match = (analysis.category.lower() == data["gold_category"].lower())
                notif_match = (predicted_should_notify == gold_should_notify)
                
                if cat_match:
                    correct_category += 1
                if notif_match:
                    correct_notification += 1
                total += 1
                
                results.append({
                    "subject": data["subject"],
                    "gold_cat": data["gold_category"],
                    "pred_cat": analysis.category,
                    "gold_score": data["gold_importance_score"],
                    "pred_score": analysis.importance_score,
                })
            except Exception as exc:
                logger.error("Error evaluating %s: %s", data["subject"], exc)
                
    if total > 0:
        logger.info("=== EVAL RESULTS ===")
        logger.info("Category Accuracy: %.1f%%", (correct_category / total) * 100)
        logger.info("Notification Accuracy: %.1f%%", (correct_notification / total) * 100)
        
        with open("EVAL_RESULTS.md", "w") as f:
            f.write("# Eval Results\n\n")
            f.write(f"- **Category Accuracy:** {(correct_category / total) * 100:.1f}%\n")
            f.write(f"- **Notification Accuracy:** {(correct_notification / total) * 100:.1f}%\n\n")
            f.write("| Subject | Gold Cat | Pred Cat | Gold Score | Pred Score |\n")
            f.write("|---------|----------|----------|------------|------------|\n")
            for r in results:
                f.write(f"| {r['subject']} | {r['gold_cat']} | {r['pred_cat']} | {r['gold_score']} | {r['pred_score']} |\n")

if __name__ == "__main__":
    run_eval()
