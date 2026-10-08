(ns shop.pricing
  (:require [clojure.string :as str]))

(def rate 2)

(defn base-price [amount]
  (* amount rate))

(defn describe [amount]
  (str/join " " ["price" (base-price amount)]))
