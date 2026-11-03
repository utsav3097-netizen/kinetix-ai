"""Solve real reference-food portions; label calories stay distinct from 4/4/9 targets."""
from itertools import combinations
from math import isfinite

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.models import Food
from app.nutrition_schemas import FoodSnapshot
from app.services.nutrition_algorithms import scale_snapshot, sum_nutrients


class MealExamples:
    def __init__(self, db, owner_id):
        foods = list(db.scalars(select(Food).where(Food.deleted_at.is_(None),
            or_(Food.owner_id.is_(None), Food.owner_id == owner_id)).order_by(Food.id)))
        # Prefer canonical identities, never their old labels/nutrient constants.
        preferred = [row for key in ("chicken-breast", "cooked-rice", "olive-oil") for row in foods if row.seed_key == key]
        # A compact deterministic set of the most macro-selective available foods.
        candidates = {row.id: row for row in preferred}
        for nutrient in ("protein_g", "carbs_g", "fat_g"):
            ranked = sorted(foods, key=lambda row: (-getattr(row, nutrient) / max(row.protein_g + row.carbs_g + row.fat_g, 1e-9), -getattr(row, nutrient), row.id))
            candidates.update((row.id, row) for row in ranked[:6] if getattr(row, nutrient) > 0)
        self.foods = list(candidates.values())
        self.cache = {}

    @staticmethod
    def solve(foods, target):
        matrix = [[getattr(food, key) / 100 for food in foods] + [target[key]]
                  for key in ("protein_g", "carbs_g", "fat_g")]
        for col in range(3):
            pivot = max(range(col, 3), key=lambda row: abs(matrix[row][col]))
            if abs(matrix[pivot][col]) < 1e-10:
                return None
            matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
            divisor = matrix[col][col]
            matrix[col] = [value / divisor for value in matrix[col]]
            for row in range(3):
                if row != col:
                    factor = matrix[row][col]
                    matrix[row] = [a - factor * b for a, b in zip(matrix[row], matrix[col])]
        grams = [matrix[row][3] for row in range(3)]
        return grams if all(isfinite(value) and 0.01 <= value <= 15000 for value in grams) else None

    def for_targets(self, target):
        key = tuple(target[nutrient] for nutrient in ("protein_g", "carbs_g", "fat_g"))
        if key in self.cache:
            return self.cache[key]
        for foods in combinations(self.foods, 3):
            quantities = self.solve(foods, target)
            if quantities is not None:
                break
        else:
            raise HTTPException(422, "Sample meals need available protein, carbohydrate and fat foods whose real nutrient basis can satisfy these macros. Add suitable foods or revise targets.")
        meals = []
        for slot, fraction in (("breakfast", 1 / 3), ("lunch", 1 / 3), ("dinner", 1 / 3)):
            items = []
            for food, quantity in zip(foods, quantities):
                snapshot = FoodSnapshot.model_validate(food, from_attributes=True).model_dump()
                grams = quantity * fraction
                items.append({"food_id": food.id, "grams": grams, "food_snapshot": snapshot,
                              "nutrients": scale_snapshot(snapshot, grams)})
            meals.append({"slot": slot, "title": " + ".join(food.name for food in foods), "items": items,
                          "totals": sum_nutrients([item["nutrients"] for item in items])})
        result = (meals, sum_nutrients([meal["totals"] for meal in meals]))
        self.cache[key] = result
        return result
